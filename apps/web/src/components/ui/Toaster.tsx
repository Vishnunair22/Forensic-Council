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
      bg: "bg-[#02040A]/80",
      border: "border-white/10",
      text: "text-white/80",
      stripe: "bg-[var(--color-primary)]/40",
    },
    success: {
      bg: "bg-[#02040A]/80",
      border: "border-[var(--color-primary)]/20",
      text: "text-[var(--color-primary)]",
      stripe: "bg-[var(--color-primary)]",
    },
    destructive: {
      bg: "bg-[#02040A]/80",
      border: "border-[var(--color-danger)]/20",
      text: "text-[var(--color-danger)]",
      stripe: "bg-[var(--color-danger)]",
    },
    warning: {
      bg: "bg-[#02040A]/80",
      border: "border-[var(--color-warning)]/20",
      text: "text-[var(--color-warning)]",
      stripe: "bg-[var(--color-warning)]",
    },
    info: {
      bg: "bg-[#02040A]/80",
      border: "border-[var(--color-primary)]/20",
      text: "text-[var(--color-primary)]",
      stripe: "bg-[var(--color-primary)]",
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
        "relative flex items-start gap-3.5 px-4 py-3.5 rounded-xl border backdrop-blur-2xl shadow-[0_0_80px_-20px_rgba(0,0,0,0.8)] overflow-hidden",
        "animate-in slide-in-from-right-full fade-in duration-300",
        style.bg,
        style.border,
      )}
      style={{ minWidth: 300, maxWidth: 420 }}
      role="alert"
      aria-live="assertive"
    >
      {/* Left accent stripe */}
      <div className={clsx("absolute left-0 top-3 bottom-3 w-[3px] rounded-full", style.stripe)} />

      <div className={clsx("w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ml-1", style.text)}
        style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}
      >
        <Icon className="w-3.5 h-3.5" />
      </div>

      <div className="flex-1 min-w-0 py-0.5">
        {t.title && (
          <p className={clsx("text-[12px] font-bold leading-tight", style.text)}>
            {t.title}
          </p>
        )}
        {t.description && (
          <p className="text-[11px] font-mono text-muted-secondary leading-relaxed mt-1">
            {t.description}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="p-1 rounded-lg text-white/18 hover:text-white/60 transition-colors duration-150 shrink-0 mt-0.5"
        aria-label="Dismiss"
      >
        <X className="w-3 h-3" />
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
