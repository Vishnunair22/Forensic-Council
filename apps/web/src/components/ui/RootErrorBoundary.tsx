"use client";

import { Component, ReactNode } from "react";
import { AlertTriangle, Home, RefreshCcw, Terminal } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class RootErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(_error: Error, _errorInfo: React.ErrorInfo) {
    // Clear only transient flow-control flags so no stale overlay/loading state
    // survives the error boundary recovery. Preserve critical investigation data
    // (SESSION_ID, INVESTIGATION_CTX, HISTORY, agent caches) so the user does
    // not lose an ongoing investigation due to a transient rendering error.
    try {
      const FLOW_CONTROL_PREFIXES = [
        "fc_show_loading", "fc_loading_", "fc_handoff",
        "fc_pending_file", "fc_hard_refresh", "fc_no_reconnect",
        "fc_arbiter_", "fc_report_ready", "fc_resume_",
        "forensic_auto_start",
      ];
      const keysToRemove: string[] = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        if (key && FLOW_CONTROL_PREFIXES.some((p) => key.startsWith(p))) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach((k) => sessionStorage.removeItem(k));
    } catch {
      // Storage might be full or disabled — safe to ignore
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.href = "/";
  };

  handleReload = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      const errorCode = "0xFC_ROOT_ERR";
      const utcStamp = new Date().toISOString().split("T")[1].slice(0, 8);

      return (
        <div className="min-h-screen flex items-center justify-center bg-background p-4">
          <div className="relative w-full max-w-xl overflow-hidden fc-surface-overlay border-[var(--color-danger)]/30 rounded-3xl">
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[var(--color-danger)]/50 to-transparent" />
            <div className="p-8 sm:p-10 flex flex-col text-left">
              <div className="flex items-center gap-3 mb-8">
                <div className="w-8 h-8 flex items-center justify-center border border-[var(--color-danger)]/30 rounded bg-[var(--color-danger)]/5">
                  <AlertTriangle className="w-4 h-4 text-[var(--color-danger)]" />
                </div>
                <span className="fc-eyebrow text-[var(--color-danger)]/60">
                  Application Error
                </span>
              </div>

              <h2 className="text-3xl font-heading font-bold text-white mb-4">
                Forensic Council Encountered an Error
              </h2>
              <p className="text-sm font-medium fc-text-faint leading-relaxed mb-8">
                {this.state.error?.message || "An unexpected error occurred in the application."}
              </p>

              <div className="flex flex-col gap-8">
                <div className="border-t border-b border-[var(--color-danger)]/10 py-4 space-y-3">
                  <div className="flex items-center gap-2 fc-eyebrow text-[var(--color-danger)]/40 mb-2">
                    <Terminal className="w-3 h-3" />
                    <span>Diagnostic Trace</span>
                  </div>
                  <div className="flex justify-between items-center text-xs font-mono">
                    <span className="fc-text-faint">Error ID</span>
                    <span className="text-[var(--color-danger)] font-bold">{errorCode}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs font-mono">
                    <span className="fc-text-faint">UTC Time</span>
                    <span className="fc-text-muted">{utcStamp}</span>
                  </div>
                </div>

                <div className="flex gap-4">
                  <button
                    type="button"
                    onClick={this.handleReset}
                    className="flex-1 fc-btn-secondary gap-2 flex items-center justify-center"
                  >
                    <Home className="w-4 h-4" />
                    Return Home
                  </button>
                  <button
                    type="button"
                    onClick={this.handleReload}
                    className="flex-1 fc-btn-danger gap-2 flex items-center justify-center"
                  >
                    <RefreshCcw className="w-4 h-4" />
                    Reload Page
                  </button>
                </div>
              </div>

              <div className="mt-8 pt-6 border-t border-white/5 flex items-center justify-between text-xs font-mono fc-text-faint tracking-widest">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-danger)] animate-pulse" />
                  <span>Pipeline Halted</span>
                </div>
                <span>Secured Session // Void</span>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
