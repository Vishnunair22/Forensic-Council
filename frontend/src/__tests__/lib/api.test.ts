/**
 * API Client Tests
 * ===============
 * 
 * Tests for the Forensic Council API client.
 */

import {
  startInvestigation,
  getReport,
  submitHITLDecision,
  type ReportDTO,
  type InvestigationResponse,
} from '@/lib/api';

// Mock global fetch
global.fetch = jest.fn();

describe('API Client', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('startInvestigation', () => {
    const mockFile = new File(['test'], 'test.jpg', { type: 'image/jpeg' });

    it('sends correct multipart form data', async () => {
      // Mock fetch to return success
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'test-123',
          case_id: 'CASE-1',
          status: 'started',
          message: 'Investigation started',
        }),
      });

      const result = await startInvestigation(mockFile, 'CASE-1', 'INVESTIGATOR-1');

      // Assert fetch was called with POST
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/investigate'),
        expect.objectContaining({
          method: 'POST',
        })
      );

      // Get the fetch call
      const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
      const formData = fetchCall[1]?.body as FormData;

      // Verify FormData contents
      expect(formData.get('file')).toBe(mockFile);
      expect(formData.get('case_id')).toBe('CASE-1');
      expect(formData.get('investigator_id')).toBe('INVESTIGATOR-1');

      // Verify returned session_id
      expect(result.session_id).toBe('test-123');
    });

    it('throws on server error', async () => {
      // Mock fetch to return 500 error
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Internal server error' }),
      });

      await expect(startInvestigation(mockFile, 'CASE-1', 'INVESTIGATOR-1')).rejects.toThrow(
        'Internal server error'
      );
    });
  });

  describe('getReport', () => {
    it('returns in_progress on 202', async () => {
      // Mock fetch to return 202
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        status: 202,
      });

      const result = await getReport('any-id');

      expect(result).toEqual({ status: 'in_progress' });
    });

    it('returns complete with report on 200', async () => {
      const mockReport: ReportDTO = {
        report_id: 'report-123',
        session_id: 'session-123',
        case_id: 'CASE-1',
        executive_summary: 'Test summary',
        per_agent_findings: {},
        cross_modal_confirmed: [],
        contested_findings: [],
        tribunal_resolved: [],
        incomplete_findings: [],
        uncertainty_statement: 'No uncertainty',
        cryptographic_signature: 'sig123',
        report_hash: 'hash123',
        signed_utc: '2024-01-01T00:00:00Z',
      };

      // Mock fetch to return 200 with report
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        status: 200,
        json: async () => mockReport,
      });

      const result = await getReport('any-id');

      expect(result).toEqual({ status: 'complete', report: mockReport });
    });

    it('throws on 404', async () => {
      // Mock fetch to return 404
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        status: 404,
      });

      await expect(getReport('any-id')).rejects.toThrow('Session not found');
    });
  });

  describe('submitHITLDecision', () => {
    it('sends correct decision payload', async () => {
      // Mock fetch to return success
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
      });

      const decision = {
        session_id: 'session-123',
        checkpoint_id: 'checkpoint-123',
        agent_id: 'Agent1_ImageIntegrity',
        decision: 'APPROVE' as const,
        note: 'Looks good',
      };

      await submitHITLDecision(decision);

      // Assert fetch was called with correct parameters
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/hitl/decision'),
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(decision),
        })
      );
    });

    it('throws on error', async () => {
      // Mock fetch to return error
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: 'Invalid decision' }),
      });

      await expect(
        submitHITLDecision({
          session_id: 'session-123',
          checkpoint_id: 'checkpoint-123',
          agent_id: 'Agent1',
          decision: 'APPROVE',
        })
      ).rejects.toThrow('Invalid decision');
    });
  });
});
