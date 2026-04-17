"use client";

import { useToast, type ToasterToast } from "@/hooks/use-toast";
import { clsx } from "clsx";
import {
  X,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Info,
} from "lucide-react";

const ICON_MAP = {
  default: Info,
  success: CheckCircle2,
  destructive: AlertCircle,
  warning: AlertTriangle,
  info: Info,
} as const;

const STYLE_MAP: Record<string, { bg: string; border: string; text: string }> =
  {
    default: {
      bg: "bg-slate-800/90",
      border: "border-slate-600/40",
      text: "text-slate-200",
    },
    success: {
      bg: "bg-emerald-900/30",
      border: "border-emerald-500/30",
      text: "text-emerald-300",
    },
    destructive: {
      bg: "bg-red-900/30",
      border: "border-red-500/30",
      text: "text-red-300",
    },
    warning: {
      bg: "bg-amber-900/30",
      border: "border-amber-500/30",
      text: "text-amber-300",
    },
    info: {
      bg: "bg-cyan-900/20",
      border: "border-cyan-500/20",
      text: "text-cyan-300",
    },
  };

function ToastCard({
  t,
  onDismiss,
}: {
  t: ToasterToast;
  onDismiss: () => void;
}) {
  const variant = t.variant || t.type || "default";
  const style = STYLE_MAP[variant] ?? STYLE_MAP.default;
  const Icon = ICON_MAP[variant] ?? Info;

  return (
    <div
      className={clsx(
        "flex items-start gap-3 p-3.5 rounded-xl border backdrop-blur-lg shadow-lg",
        "animate-in slide-in-from-right-full fade-in duration-200",
        style.bg,
        style.border,
      )}
      style={{ minWidth: 280, maxWidth: 420 }}
      role="alert"
      aria-live="assertive"
    >
      <Icon className={clsx("w-4 h-4 shrink-0 mt-0.5", style.text)} />
      <div className="flex-1 min-w-0">
        {t.title && (
          <p className={clsx("text-xs font-bold leading-tight", style.text)}>
            {t.title}
          </p>
        )}
        {t.description && (
          <p className="text-[11px] text-foreground/60 leading-relaxed mt-0.5">
            {t.description}
          </p>
        )}
      </div>
      <button
        onClick={onDismiss}
        className="p-1 rounded-md hover:bg-white/10 text-foreground/30 hover:text-foreground/60 transition-colors shrink-0"
        aria-label="Dismiss"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

export function Toaster() {
  const { toasts, dismiss } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none"
      aria-label="Notifications"
    >
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <ToastCard t={t} onDismiss={() => dismiss(t.id)} />
        </div>
      ))}
    </div>
  );
}
