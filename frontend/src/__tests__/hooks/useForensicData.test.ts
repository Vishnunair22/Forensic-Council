/**
 * useForensicData Hook Tests
 * ==========================
 * 
 * Tests for the useForensicData React hook.
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { useForensicData } from '@/hooks/useForensicData';
import * as api from '@/lib/api';

// Mock the API module
jest.mock('@/lib/api', () => ({
  startInvestigation: jest.fn(),
  getReport: jest.fn(),
}));

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: jest.fn((key: string) => store[key] || null),
    setItem: jest.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: jest.fn((key: string) => {
      delete store[key];
    }),
    clear: jest.fn(() => {
      store = {};
    }),
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

describe('useForensicData', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorageMock.clear();
  });

  it('starts analysis and returns session ID', async () => {
    const mockFile = new File(['test'], 'test.jpg', { type: 'image/jpeg' });
    
    (api.startInvestigation as jest.Mock).mockResolvedValueOnce({
      session_id: 'abc-123',
    });

    const { result } = renderHook(() => useForensicData());

    // Wait for initial load
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    // Call startAnalysis
    const sessionId = await result.current.startAnalysis(mockFile, 'CASE-1', 'INVESTIGATOR-1');

    // Verify API was called
    expect(api.startInvestigation).toHaveBeenCalledWith(
      mockFile,
      'CASE-1',
      'INVESTIGATOR-1'
    );

    // Verify returned session ID
    expect(sessionId).toBe('abc-123');
  });

  it('getCurrentReport returns null before complete', () => {
    const { result } = renderHook(() => useForensicData());

    // Wait for initial load
    expect(result.current.isLoading).toBe(true);

    // getCurrentReport should return null
    expect(result.current.getCurrentReport()).toBeNull();
  });

  it('validates file correctly', async () => {
    const { result } = renderHook(() => useForensicData());

    // Wait for initial load
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    // Test valid file
    const validFile = new File(['test'], 'test.jpg', { type: 'image/jpeg' });
    Object.defineProperty(validFile, 'size', { value: 1024 * 1024 }); // 1MB
    expect(result.current.validateFile(validFile)).toEqual({ valid: true });

    // Test file too large
    const largeFile = new File(['test'], 'test.jpg', { type: 'image/jpeg' });
    Object.defineProperty(largeFile, 'size', { value: 100 * 1024 * 1024 }); // 100MB
    expect(result.current.validateFile(largeFile)).toEqual({
      valid: false,
      error: 'File exceeds 50MB limit.',
    });

    // Test invalid type
    const invalidFile = new File(['test'], 'test.txt', { type: 'text/plain' });
    Object.defineProperty(invalidFile, 'size', { value: 1024 });
    expect(result.current.validateFile(invalidFile)).toEqual({
      valid: false,
      error: 'Unsupported format. Use JPG, PNG, MP4, WAV, or MPEG.',
    });
  });

  it('saves and retrieves current report', async () => {
    const { result } = renderHook(() => useForensicData());

    // Wait for initial load
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const mockReport = {
      id: 'report-123',
      fileName: 'test.jpg',
      timestamp: '2024-01-01T00:00:00Z',
      summary: 'Test summary',
      agents: [],
    };

    // Save report
    result.current.saveCurrentReport(mockReport);

    // Retrieve report
    expect(result.current.getCurrentReport()).toEqual(mockReport);
  });

  it('adds to history', async () => {
    const { result } = renderHook(() => useForensicData());

    // Wait for initial load
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const mockReport = {
      id: 'report-123',
      fileName: 'test.jpg',
      timestamp: '2024-01-01T00:00:00Z',
      summary: 'Test summary',
      agents: [],
    };

    // Add to history
    result.current.addToHistory(mockReport);

    // Verify history contains the report
    expect(result.current.getHistory()).toContainEqual(mockReport);
  });

  it('clears history', async () => {
    const { result } = renderHook(() => useForensicData());

    // Wait for initial load
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const mockReport = {
      id: 'report-123',
      fileName: 'test.jpg',
      timestamp: '2024-01-01T00:00:00Z',
      summary: 'Test summary',
      agents: [],
    };

    // Add to history
    result.current.addToHistory(mockReport);
    expect(result.current.getHistory().length).toBe(1);

    // Clear history
    result.current.clearHistory();

    // Verify history is empty
    expect(result.current.getHistory()).toEqual([]);
  });
});
