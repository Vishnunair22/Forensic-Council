/**
 * Forensic Council Load Test
 * ==========================
 *
 * Minimal k6 script to verify forensic pipeline performance.
 * Run with: k6 run tests/load/forensic_pipeline.js
 *
 * Requirements:
 * - API running at http://localhost:8000
 * - Valid auth token (set via environment or update the script)
 *
 * Environment variables:
 * - K6_API_URL: Base URL (default: http://localhost:8000)
 * - K6_AUTH_TOKEN: Authentication token
 * - K6_TEST_FILE: Path to test file to upload (default: fixtures/test_image.webp)
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const BASE_URL = __ENV.K6_API_URL || 'http://localhost:8000';
const AUTH_TOKEN = __ENV.K6_AUTH_TOKEN || '';
const TEST_FILE = __ENV.K6_TEST_FILE || '../../tests/fixtures/test_image.webp';

const errorRate = new Rate('errors');

export const options = {
  scenarios: {
    // 5 concurrent forensic analyses
    concurrent_analysis: {
      executor: 'per-vu-iterations',
      vus: 5,
      iterations: 1,
      maxDuration: '10m',
    },
  },
  thresholds: {
    // Assert P95 < 120s for initial pass
    http_req_duration: ['p(95)<120000'],
    errors: ['rate<0.1'],
  },
};

function getAuthToken() {
  if (AUTH_TOKEN) return AUTH_TOKEN;

  const loginRes = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    'username=investigator&password=admin',
    {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }
  );

  if (loginRes.status !== 200) {
    throw new Error(`Login failed: ${loginRes.status} ${loginRes.body}`);
  }

  const setCookie = loginRes.headers['Set-Cookie'];
  const tokenMatch = setCookie?.match(/access_token=([^;]+)/);
  return tokenMatch ? tokenMatch[1] : '';
}

function startInvestigation(token, filePath) {
  const file = open(filePath, 'b');
  const formData = new FormData();
  formData.append('file', file, 'test_image.webp');
  formData.append('case_id', `LOAD_TEST_${Date.now()}`);
  formData.append('investigator_id', 'load-test-user');

  const res = http.post(
    `${BASE_URL}/api/v1/investigate`,
    formData,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    }
  );

  return res;
}

function pollForCompletion(sessionId, token) {
  const maxAttempts = 120; // 2 minutes max
  let attempts = 0;

  while (attempts < maxAttempts) {
    const res = http.get(
      `${BASE_URL}/api/v1/sessions/${sessionId}/arbiter-status`,
      {
        headers: { 'Authorization': `Bearer ${token}` },
      }
    );

    if (res.status === 200) {
      const data = JSON.parse(res.body);
      if (data.status === 'complete') {
        return true;
      }
      if (data.status === 'error') {
        return false;
      }
    }

    sleep(1);
    attempts++;
  }

  return false; // Timeout
}

export default function () {
  const token = getAuthToken();

  if (!token) {
    errorRate.add(1);
    throw new Error('Failed to obtain auth token');
  }

  // Start investigation
  const startRes = startInvestigation(token, TEST_FILE);

  const startCheck = check(startRes, {
    'investigation started': (r) => r.status === 200 || r.status === 201,
  });

  if (!startCheck) {
    errorRate.add(1);
    console.error(`Investigation failed: ${startRes.status} ${startRes.body}`);
    return;
  }

  const startData = JSON.parse(startRes.body);
  const sessionId = startData.session_id;

  // Poll for completion
  const completed = pollForCompletion(sessionId, token);

  const finalCheck = check(completed, {
    'analysis completed within timeout': (r) => r === true,
  });

  if (!finalCheck) {
    errorRate.add(1);
    console.error(`Analysis did not complete for session ${sessionId}`);
  }

  sleep(1);
}

export function handleSummary(data) {
  return {
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
    'tests/load/summary.json': JSON.stringify(data, null, 2),
  };
}

function textSummary(data, options) {
  const indent = options.indent || '';
  const enableColors = options.enableColors || false;

  let output = `${indent}Load Test Results\n`;
  output += `${indent=====================\n\n`;

  if (data.metrics.http_req_duration) {
    const duration = data.metrics.http_req_duration;
    output += `${indent}HTTP Request Duration:\n`;
    output += `${indent}  p(95): ${(duration['p(95)'] / 1000).toFixed(2)}s\n`;
    output += `${indent}  p(99): ${(duration['p(99)'] / 1000).toFixed(2)}s\n`;
    output += `${indent}  avg:  ${(duration.avg / 1000).toFixed(2)}s\n\n`;
  }

  if (data.metrics.errors) {
    output += `${indent}Error Rate: ${(data.metrics.errors.values.rate * 100).toFixed(2)}%\n`;
  }

  output += `\n${indent}Threshold Check: p(95) < 120s\n`;
  const p95 = data.metrics.http_req_duration?.['p(95)'] || 0;
  const passed = p95 < 120000;
  output += `${indent}Result: ${passed ? 'PASSED' : 'FAILED'}\n`;

  return output;
}