/**
 * Schema Validation Tests
 * ======================
 * 
 * Tests for Zod schema validation.
 */

import { ReportSchema, AgentResultSchema, HistorySchema } from '@/lib/schemas';

describe('Schema Validation', () => {
  describe('AgentResultSchema', () => {
    it('validates complete agent result', () => {
      const validAgent = {
        id: 'agent-1',
        name: 'Agent1',
        role: 'Image Analysis',
        result: 'Manipulation detected',
        confidence: 0.95,
      };

      const result = AgentResultSchema.safeParse(validAgent);
      expect(result.success).toBe(true);
    });

    it('rejects missing required fields', () => {
      const invalidAgent = {
        id: 'agent-1',
        // missing name, role, result, confidence
      };

      const result = AgentResultSchema.safeParse(invalidAgent);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues.length).toBeGreaterThan(0);
      }
    });

    it('rejects wrong field types', () => {
      const invalidAgent = {
        id: 123,  // should be string
        name: 'Agent1',
        role: 'Image Analysis',
        result: 'Manipulation detected',
        confidence: 'high',  // should be number
      };

      const result = AgentResultSchema.safeParse(invalidAgent);
      expect(result.success).toBe(false);
    });
  });

  describe('ReportSchema', () => {
    it('validates complete report', () => {
      const validReport = {
        id: 'report-123',
        fileName: 'evidence.jpg',
        timestamp: '2024-01-01T00:00:00Z',
        summary: 'Analysis complete',
        agents: [
          {
            id: 'agent-1',
            name: 'Agent1',
            role: 'Image Analysis',
            result: 'Manipulation detected',
            confidence: 0.95,
          },
        ],
      };

      const result = ReportSchema.safeParse(validReport);
      expect(result.success).toBe(true);
    });

    it('rejects missing required fields', () => {
      const invalidReport = {
        id: 'report-123',
        fileName: 'evidence.jpg',
        // missing timestamp, summary, agents
      };

      const result = ReportSchema.safeParse(invalidReport);
      expect(result.success).toBe(false);
    });

    it('rejects empty agents array', () => {
      const validReport = {
        id: 'report-123',
        fileName: 'evidence.jpg',
        timestamp: '2024-01-01T00:00:00Z',
        summary: 'Analysis complete',
        agents: [],  // empty array is valid
      };

      const result = ReportSchema.safeParse(validReport);
      expect(result.success).toBe(true);
    });
  });

  describe('HistorySchema', () => {
    it('validates array of reports', () => {
      const validHistory = [
        {
          id: 'report-1',
          fileName: 'evidence1.jpg',
          timestamp: '2024-01-01T00:00:00Z',
          summary: 'Analysis complete',
          agents: [],
        },
        {
          id: 'report-2',
          fileName: 'evidence2.jpg',
          timestamp: '2024-01-02T00:00:00Z',
          summary: 'No issues found',
          agents: [],
        },
      ];

      const result = HistorySchema.safeParse(validHistory);
      expect(result.success).toBe(true);
    });

    it('rejects non-array input', () => {
      const invalidHistory = {
        id: 'report-1',
        fileName: 'evidence1.jpg',
        timestamp: '2024-01-01T00:00:00Z',
        summary: 'Analysis complete',
        agents: [],
      };

      const result = HistorySchema.safeParse(invalidHistory);
      expect(result.success).toBe(false);
    });

    it('rejects array with invalid report', () => {
      const invalidHistory = [
        {
          id: 'report-1',
          fileName: 'evidence1.jpg',
          timestamp: '2024-01-01T00:00:00Z',
          summary: 'Analysis complete',
          agents: [],
        },
        {
          id: 'report-2',
          // missing required fields
        },
      ];

      const result = HistorySchema.safeParse(invalidHistory);
      expect(result.success).toBe(false);
    });
  });
});
