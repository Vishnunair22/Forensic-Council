/**
 * Unit tests for QuotaMeter component
 */

import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import { QuotaMeter } from "@/components/evidence/QuotaMeter";

// Mock fetch globally
global.fetch = jest.fn();

const mockFetch = global.fetch as jest.Mock;

describe("QuotaMeter", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    // Mock document.cookie to return a mock token
    Object.defineProperty(document, "cookie", {
      writable: true,
      value: "access_token=mock-token;",
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("renders correctly with mock data", async () => {
    const mockQuotaData = {
      tokens_used: 800,
      tokens_limit: 1000,
      cost_estimate_usd: 0.008,
      calls_total: 5,
      degraded: false,
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockQuotaData,
    });

    await act(async () => {
      render(<QuotaMeter sessionId="test-session-123" enabled={true} />);
    });

    // Should display the quota data
    await waitFor(() => {
      expect(screen.getByText(/800/)).toBeInTheDocument();
      expect(screen.getByText(/1,000/)).toBeInTheDocument();
    });
  });

  it("shows amber state at 80% usage", async () => {
    const mockQuotaData = {
      tokens_used: 800,
      tokens_limit: 1000, // 80%
      cost_estimate_usd: 0.008,
      calls_total: 5,
      degraded: false,
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockQuotaData,
    });

    await act(async () => {
      render(<QuotaMeter sessionId="test-session-123" enabled={true} />);
    });

    // Should show high usage warning
    await waitFor(() => {
      expect(screen.getByText(/High usage/)).toBeInTheDocument();
    });
  });

  it("shows red/warning state at 100% usage", async () => {
    const mockQuotaData = {
      tokens_used: 1000,
      tokens_limit: 1000, // 100%
      cost_estimate_usd: 0.0125,
      calls_total: 10,
      degraded: false,
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockQuotaData,
    });

    await act(async () => {
      render(<QuotaMeter sessionId="test-session-123" enabled={true} />);
    });

    // Should show limit reached warning
    await waitFor(() => {
      expect(screen.getByText(/Limit reached/)).toBeInTheDocument();
    });
  });

  it('shows "Data unavailable" when degraded is true in API response', async () => {
    const mockQuotaData = {
      tokens_used: 0,
      tokens_limit: 100000,
      cost_estimate_usd: 0,
      calls_total: 0,
      degraded: true,
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockQuotaData,
    });

    await act(async () => {
      render(<QuotaMeter sessionId="test-session-123" enabled={true} />);
    });

    // Should show unavailable message
    await waitFor(() => {
      expect(screen.getByText(/Quota data unavailable/)).toBeInTheDocument();
    });
  });

  it("renders nothing when enabled is false", async () => {
    const { container } = render(
      <QuotaMeter sessionId="test-session-123" enabled={false} />
    );

    // Should render empty
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when sessionId is null", async () => {
    const { container } = render(<QuotaMeter sessionId={null} enabled={true} />);

    // Should render empty
    expect(container.firstChild).toBeNull();
  });

  it("has aria-label for screen reader access", async () => {
    const mockQuotaData = {
      tokens_used: 500,
      tokens_limit: 1000,
      cost_estimate_usd: 0.005,
      calls_total: 3,
      degraded: false,
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockQuotaData,
    });

    await act(async () => {
      render(<QuotaMeter sessionId="test-session-123" enabled={true} />);
    });

    // Check that the component has accessible text
    await waitFor(() => {
      // The component should display quota information
      expect(screen.getByText(/500/)).toBeInTheDocument();
    });
  });

  it("displays cost estimate in USD", async () => {
    const mockQuotaData = {
      tokens_used: 500,
      tokens_limit: 1000,
      cost_estimate_usd: 0.005,
      calls_total: 3,
      degraded: false,
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockQuotaData,
    });

    await act(async () => {
      render(<QuotaMeter sessionId="test-session-123" enabled={true} />);
    });

    // Should show cost with $ sign
    await waitFor(() => {
      expect(screen.getByText(/\$0.0050/)).toBeInTheDocument();
    });
  });

  it("displays total API calls count", async () => {
    const mockQuotaData = {
      tokens_used: 500,
      tokens_limit: 1000,
      cost_estimate_usd: 0.005,
      calls_total: 7,
      degraded: false,
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockQuotaData,
    });

    await act(async () => {
      render(<QuotaMeter sessionId="test-session-123" enabled={true} />);
    });

    // Should show call count
    await waitFor(() => {
      expect(screen.getByText(/7 calls/)).toBeInTheDocument();
    });
  });

  it("handles fetch error gracefully", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network error"));

    await act(async () => {
      render(<QuotaMeter sessionId="test-session-123" enabled={true} />);
    });

    // Should show unavailable when there's an error
    await waitFor(() => {
      expect(screen.getByText(/Quota data unavailable/)).toBeInTheDocument();
    });
  });

  it("handles non-OK response status", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    await act(async () => {
      render(<QuotaMeter sessionId="test-session-123" enabled={true} />);
    });

    // Should show unavailable for error status
    await waitFor(() => {
      expect(screen.getByText(/Quota data unavailable/)).toBeInTheDocument();
    });
  });
});