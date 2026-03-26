"use client";

import React, { Component, ErrorInfo, ReactNode, useEffect, useState } from "react";
import { AlertTriangle, Terminal, Cpu, Network, WifiOff, AlertCircle, FileJson, Bug, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";

// =========================================================================
// Error Classification Logic
// =========================================================================

type ErrorCategory =
  | "REACT_CRASH"
  | "NETWORK_ERROR"
  | "WEBSOCKET_ERROR"
  | "API_ERROR"
  | "NULL_REFERENCE"
  | "MODULE_ERROR"
  | "RUNTIME_ERROR";

interface ParsedError {
  category: ErrorCategory;
  title: string;
  message: string;
  stack: string;
  componentStack?: string;
  isCustom: boolean;
}

const classifyError = (error: Error, componentStack?: string): ParsedError => {
  const msg = error.message?.toLowerCase() || "";
  const stack = error.stack || "";

  let category: ErrorCategory = "RUNTIME_ERROR";
  let title = error.name || "Error";

  // 1. WebSocket Errors
  if (msg.includes("websocket") || msg.includes("ws://") || msg.includes("connection closed")) {
    category = "WEBSOCKET_ERROR";
    title = "WebSocket Connection Failure";
  }
  // 2. Network / Fetch Errors
  else if (msg.includes("fetch") || msg.includes("network error") || msg.includes("cors") || msg.includes("failed to fetch")) {
    category = "NETWORK_ERROR";
    title = "Network / Fetch Payload Failed";
  }
  // 3. API / 4xx 5xx Errors
  else if (msg.includes("40") || msg.includes("50") || msg.includes("api error") || msg.includes("unauthorized")) {
    category = "API_ERROR";
    title = "Backend API Execution Error";
  }
  // 4. Null References (Classic JS)
  else if (msg.includes("undefined") || msg.includes("null") || msg.includes("is not a function") || msg.includes("read properties of")) {
    category = "NULL_REFERENCE";
    title = "Null Reference Exception";
  }
  // 5. Module / Import Errors
  else if (msg.includes("module not found") || msg.includes("import") || msg.includes("failed to resolve")) {
    category = "MODULE_ERROR";
    title = "Module / Dependency Missing";
  }
  // 6. React Component Crashes
  else if (componentStack || msg.includes("rendering") || msg.includes("minified react error")) {
    category = "REACT_CRASH";
    title = "React Component Render Crash";
  }

  return {
    category,
    title,
    message: error.message || "An unknown error occurred.",
    stack,
    componentStack,
    isCustom: true
  };
};

const getGuidesForCategory = (category: ErrorCategory) => {
  switch (category) {
    case "WEBSOCKET_ERROR":
      return [
        "Check if `backend` container is running and healthy: `docker ps`",
        "Verify `useSimulation.ts` is parsing the `BriefUpdate` schema correctly.",
        "Check Next.js standalone proxy settings (CORS) for WS upgrades.",
        "Did you hit the 300s INVESTIGATION_TIMEOUT? Subprocess might have killed the socket."
      ];
    case "NETWORK_ERROR":
      return [
        "Check `/health` endpoint directly.",
        "Verify `NEXT_PUBLIC_API_URL` environment variable matches backend port (8000).",
        "Verify CORS setup in `api.main.py` matches your frontend origin.",
        "Are you attempting to fetch from a mixed-content (HTTP vs HTTPS) origin?"
      ];
    case "API_ERROR":
      return [
        "Check `docker logs -f forensic_api` for the Python traceback.",
        "Verify Pydantic schema validation. Are you sending the correct field types?",
        "Did the Redis session expire? (`ex=86400`)",
        "Look for missing Authorization headers if Auth is implemented."
      ];
    case "NULL_REFERENCE":
      return [
        "Check state variables — are they being initialized correctly?",
        "If mapping an array, add optional chaining syntax `arr?.map(...)`.",
        "Are you querying the DOM before the component has mounted?",
        "Verify the backend JSON response actually contains the nested key you are reading."
      ];
    case "MODULE_ERROR":
      return [
        "Did you install the dependency? Run `npm install`.",
        "Check your import paths (are you using `@/` aliases properly?)",
        "Does the file exist? Case sensitivity matters in Linux/Docker vs Windows.",
        "Clear Next.js cache: `rm -rf .next` and restart dev server."
      ];
    case "REACT_CRASH":
      return [
        "Check the Component Tree tab to see exactly which node crashed.",
        "Are you using hooks conditionally? Hooks must be called at the top level.",
        "Are you returning valid JSX or accidentally returning an object?",
        "Check if a 3D component (`@react-three/fiber`) is missing a canvas wrapper."
      ];
    default:
      return [
        "Check the Stack Trace for the exact line number.",
        "Use `console.log` right before the crash points.",
        "Verify browser console for warnings that appeared immediately before the crash.",
        "Ensure Node.js and Python versions match the project requirements."
      ];
  }
};

const getIconForCategory = (category: ErrorCategory) => {
  switch (category) {
    case "WEBSOCKET_ERROR": return <WifiOff className="w-5 h-5 text-red-400" />;
    case "NETWORK_ERROR": return <Network className="w-5 h-5 text-red-400" />;
    case "API_ERROR": return <Cpu className="w-5 h-5 text-orange-400" />;
    case "NULL_REFERENCE": return <AlertCircle className="w-5 h-5 text-yellow-400" />;
    case "MODULE_ERROR": return <FileJson className="w-5 h-5 text-blue-400" />;
    case "REACT_CRASH": return <Bug className="w-5 h-5 text-rose-400" />;
    default: return <AlertTriangle className="w-5 h-5 text-neutral-400" />;
  }
};

// =========================================================================
// Error Boundary Wrappers
// =========================================================================

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class GlobalErrorBoundary extends Component<{ children: ReactNode, onErrorCaught: (e: Error, info?: string) => void }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode, onErrorCaught: (e: Error, info?: string) => void }) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    this.props.onErrorCaught(error, errorInfo.componentStack?.toString());
  }

  render() {
    // We don't block the children in Dev, we just let the overlay render on top
    // In prod, you'd want a real fallback UI here, but Next.js `error.tsx` handles that usually.
    return this.props.children;
  }
}

// =========================================================================
// Overlay Component
// =========================================================================

export function DevErrorOverlay({ errorData, onDismiss }: { errorData: ParsedError, onDismiss: () => void }) {
  const [activeTab, setActiveTab] = useState<"guides" | "stack" | "tree" | "raw">("guides");

  if (!errorData) return null;

  // Render a parsed stack trace to highlight user code
  const renderStack = () => {
    if (!errorData.stack) return <div className="p-4 text-neutral-500">No stack trace available.</div>;

    return (
      <div className="space-y-1 font-mono text-sm tracking-tight text-neutral-300 overflow-x-auto whitespace-pre p-4">
        {errorData.stack.split('\n').map((line, i) => {
          // Highlight frames that are likely "user code" (src directory)
          const isUserCode = line.includes('src/') && !line.includes('node_modules');

          if (isUserCode) {
            return (
              <div key={i} className="py-1 px-2 border-l-2 border-rose-500 bg-rose-500/10 text-rose-200">
                <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 mr-2 uppercase tracking-wider">Yours</span>
                {line.trim()}
              </div>
            );
          }
          return <div key={i} className="py-0.5 px-2 opacity-60 hover:opacity-100 transition-opacity">{line.trim()}</div>;
        })}
      </div>
    );
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="dev-error-title"
      className="fixed inset-0 z-[9999] flex flex-col bg-neutral-950/90 backdrop-blur-sm overflow-hidden font-sans tabular-nums selection:bg-rose-500/30"
    >

      {/* Header Bar */}
      <div className="flex-none bg-rose-950/40 border-b border-rose-500/20 px-6 py-4 flex items-start justify-between shadow-2xl">
        <div className="flex gap-4 items-start">
          <div className="mt-1 p-2 bg-neutral-900 rounded-lg border border-neutral-800 shadow-inner">
            {getIconForCategory(errorData.category)}
          </div>
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="px-2 py-0.5 rounded text-xs font-bold tracking-widest uppercase bg-rose-500/20 text-rose-400 border border-rose-500/20">
                {errorData.category.replace("_", " ")}
              </span>
              <h1 id="dev-error-title" className="text-xl font-semibold text-neutral-100">{errorData.title}</h1>
            </div>
            <p className="text-neutral-300 font-mono text-sm leading-relaxed max-w-4xl opacity-90">{errorData.message}</p>
          </div>
        </div>

        <button
          onClick={onDismiss}
          aria-label="Dismiss error overlay (Escape)"
          className="p-2 text-neutral-500 hover:text-white hover:bg-white/10 rounded-md transition-colors"
        >
          <X className="w-5 h-5" aria-hidden="true" />
        </button>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 min-h-0 flex flex-col">
        {/* Tabs */}
        <div className="flex px-6 bg-neutral-900 border-b border-neutral-800 pt-2 gap-1">
          {(() => {
            const tabs: { id: "guides" | "stack" | "tree" | "raw"; label: string; icon: LucideIcon }[] = [
              { id: "guides", label: "Fix Guides", icon: Terminal },
              { id: "stack", label: "Smart Stack", icon: FileJson },
              { id: "tree", label: "Component Tree", icon: Cpu },
              { id: "raw", label: "Raw Output", icon: Terminal },
            ];
            return tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as "guides" | "stack" | "tree" | "raw")}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${activeTab === tab.id
                  ? "border-rose-500 text-rose-400 bg-rose-500/5"
                  : "border-transparent text-neutral-400 hover:text-neutral-200 hover:bg-white/5"
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ));
          })()}
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto bg-neutral-950/50">

          {activeTab === "guides" && (
            <div className="p-8 max-w-4xl mx-auto space-y-6">
              <div className="mb-6 pb-2 border-b border-neutral-800">
                <h2 className="text-lg font-medium text-neutral-200 flex items-center gap-2">
                  <AlertCircle className="w-5 h-5 text-rose-400" />
                  Suggested Diagnosis
                </h2>
                <p className="text-sm text-neutral-500 mt-1">Based on the error signature, check these common Forensic Council issues:</p>
              </div>

              <div className="space-y-3">
                {getGuidesForCategory(errorData.category).map((guide, idx) => (
                  <div key={idx} className="flex gap-4 p-4 rounded-lg bg-neutral-900 border border-neutral-800 shadow-sm hover:border-neutral-700 transition-colors">
                    <div className="flex-none w-6 h-6 rounded-full bg-neutral-800 text-neutral-400 flex items-center justify-center font-mono text-xs border border-neutral-700">
                      {idx + 1}
                    </div>
                    <p className="text-neutral-300 text-sm [&>code]:text-rose-300 [&>code]:bg-rose-500/10 [&>code]:px-1.5 [&>code]:py-0.5 [&>code]:rounded [&>code]:font-mono">
                      {/* Very basic markdown inline code parser for visual flair */}
                      {guide.split(/(`[^`]+`)/g).map((part, i) => {
                        if (part.startsWith('`') && part.endsWith('`')) {
                          return <code key={i}>{part.slice(1, -1)}</code>;
                        }
                        return part;
                      })}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === "stack" && (
            <div className="h-full bg-neutral-950 overflow-auto">
              {renderStack()}
            </div>
          )}

          {activeTab === "tree" && (
            <div className="p-6 h-full bg-neutral-950 font-mono text-sm text-neutral-300 overflow-auto whitespace-pre">
              {errorData.componentStack ? (
                <div className="border-l border-neutral-800 ml-4 pl-4 space-y-1">
                  {errorData.componentStack.split('\n').filter(Boolean).map((line, i) => (
                    <div key={i} className={`py-1 ${i === 0 ? 'text-rose-400 font-bold' : 'opacity-70'}`}>
                      {line.trim()}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 text-center text-neutral-500 italic">
                  Component tree unavailable. This error occurred outside the React render cycle.
                </div>
              )}
            </div>
          )}

          {activeTab === "raw" && (
            <div className="p-6 h-full font-mono text-xs text-neutral-400 leading-relaxed overflow-auto">
              <h3 className="text-neutral-500 mb-2">{"// "} raw.stack</h3>
              {errorData.stack}

              {errorData.componentStack && (
                <>
                  <h3 className="text-neutral-500 mt-8 mb-2">{"// "} component.stack</h3>
                  {errorData.componentStack}
                </>
              )}
            </div>
          )}

        </div>
      </div>

      {/* Footer */}
      <div className="flex-none p-3 border-t border-neutral-900 bg-neutral-950 flex justify-between items-center text-xs text-neutral-600 font-mono">
        <div>DevErrorOverlay • Forensic Council Architecture</div>
        <div className="flex gap-4">
          <span>{new Date().toISOString()}</span>
          <span>NODE_ENV=development</span>
        </div>
      </div>
    </div>
  );
}

// =========================================================================
// Context Provider Export
// =========================================================================

export function DevErrorProvider({ children }: { children: ReactNode }) {
  const [errorData, setErrorData] = useState<ParsedError | null>(null);

  useEffect(() => {
    // Only run in development
    if (process.env.NODE_ENV !== 'development') return;

    const handleGlobalError = (event: ErrorEvent) => {
      // Prevent default browser console bomb (optional, often better to keep it false)
      // event.preventDefault(); 
      setErrorData(classifyError(event.error || new Error(event.message)));
    };

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      const err = event.reason instanceof Error ? event.reason : new Error(String(event.reason));
      setErrorData(classifyError(err));
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setErrorData(null);
    };

    window.addEventListener('error', handleGlobalError);
    window.addEventListener('unhandledrejection', handleUnhandledRejection);
    window.addEventListener('keydown', handleEscape);

    return () => {
      window.removeEventListener('error', handleGlobalError);
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
      window.removeEventListener('keydown', handleEscape);
    };
  }, []);

  const handleReactCrash = (error: Error, componentStack?: string) => {
    setErrorData(classifyError(error, componentStack));
  };

  // If in production, strip out the wrapper completely to save bytes and prevent  shifts
  if (process.env.NODE_ENV !== 'development') {
    return <>{children}</>;
  }

  return (
    <GlobalErrorBoundary onErrorCaught={handleReactCrash}>
      {children}
      {errorData && <DevErrorOverlay errorData={errorData} onDismiss={() => setErrorData(null)} />}
    </GlobalErrorBoundary>
  );
}
