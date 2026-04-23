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

const STYLE_MAP: Record<string, { bg: string; border: string; text: string; stripe: string }> =
  {
    default: {
      bg: "bg-surface-2/80",
      border: "border-border-subtle",
      text: "text-white/80",
      stripe: "bg-primary/40",
    },
    success: {
      bg: "bg-surface-2/90",
      border: "border-primary/20",
      text: "text-primary",
      stripe: "bg-primary",
    },
    destructive: {
      bg: "bg-surface-2/90",
      border: "border-danger/20",
      text: "text-danger",
      stripe: "bg-danger",
    },
    warning: {
      bg: "bg-surface-2/90",
      border: "border-warning/20",
      text: "text-warning",
      stripe: "bg-warning",
    },
    info: {
      bg: "bg-surface-2/90",
      border: "border-primary/20",
      text: "text-primary",
      stripe: "bg-primary",
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
        "relative flex items-start gap-4 p-4 rounded-2xl border backdrop-blur-2xl shadow-2xl overflow-hidden",
        "animate-in slide-in-from-right-full fade-in duration-300",
        style.bg,
        style.border,
      )}
      style={{ minWidth: 320, maxWidth: 440 }}
      role="alert"
      aria-live="assertive"
    >
      <div className={clsx("absolute left-0 top-0 bottom-0 w-1", style.stripe)} />
      
      <div className={clsx("w-9 h-9 rounded-xl flex items-center justify-center shrink-0 bg-surface-1 border border-border-subtle shadow-inner", style.text)}>
        <Icon className="w-4 h-4" />
      </div>

      <div className="flex-1 min-w-0">
        {t.title && (
          <p className={clsx("text-xs font-black tracking-wide leading-tight", style.text)}>
            {t.title}
          </p>
        )}
        {t.description && (
          <p className="text-[11px] font-mono font-medium text-white/40 leading-relaxed mt-1 tracking-tight">
            {t.description}
          </p>
        )}
      </div>
      <button
        onClick={onDismiss}
        className="p-1 rounded-md hover:bg-white/10 text-white/20 hover:text-white transition-colors shrink-0"
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
      className="fixed top-8 left-1/2 -translate-x-1/2 z-[9999] flex flex-col gap-2 pointer-events-none w-full max-w-md px-4"
      aria-label="Notifications"
    >
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto flex justify-center">
          <ToastCard t={t} onDismiss={() => dismiss(t.id)} />
        </div>
      ))}
    </div>
  );
}
