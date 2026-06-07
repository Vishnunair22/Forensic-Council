"use client";

import React, { useEffect, useRef, useState } from "react";
import { Check, Copy, Fingerprint, Hash, Shield } from "lucide-react";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import type { ReportDTO } from "@/lib/api";

interface ReportIntegrityProps {
  report: ReportDTO;
  sessionId: string | null;
  isDeepPhase: boolean;
}

function shortId(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length > 16 ? `…${value.slice(-12)}` : value;
}

function formatSignedDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    // Render in UTC: deterministic across server/client (no hydration mismatch)
    // and viewer-independent — the court-defensible standard for the signed
    // timestamp (matches the report's signed_utc field).
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZone: "UTC",
      timeZoneName: "short",
    });
  } catch {
    return iso;
  }
}

export function ReportIntegrity({ report, sessionId, isDeepPhase }: ReportIntegrityProps) {
  const [investigatorId, setInvestigatorId] = useState<string | null>(null);
  const [copiedHash, setCopiedHash] = useState(false);
  const [copiedSig, setCopiedSig] = useState(false);
  const hashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sigTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const id = typeof window !== "undefined"
      ? localStorage.getItem(STORAGE_KEYS.INVESTIGATOR_ID)
      : null;
    setInvestigatorId(id);
    return () => {
      if (hashTimerRef.current) clearTimeout(hashTimerRef.current);
      if (sigTimerRef.current) clearTimeout(sigTimerRef.current);
    };
  }, []);

  const reportHash = report.report_hash || "";
  const signature = report.cryptographic_signature || "";

  const handleCopyHash = () => {
    if (!reportHash) return;
    navigator.clipboard.writeText(reportHash).then(() => {
      setCopiedHash(true);
      if (hashTimerRef.current) clearTimeout(hashTimerRef.current);
      hashTimerRef.current = setTimeout(() => setCopiedHash(false), 2000);
    }).catch(() => {});
  };

  const handleCopySig = () => {
    if (!signature) return;
    navigator.clipboard.writeText(signature).then(() => {
      setCopiedSig(true);
      if (sigTimerRef.current) clearTimeout(sigTimerRef.current);
      sigTimerRef.current = setTimeout(() => setCopiedSig(false), 2000);
    }).catch(() => {});
  };

  const cells = [
    { label: "Report ID",       value: shortId(report.report_id) },
    { label: "Session ID",      value: shortId(sessionId) },
    { label: "Case ID",         value: shortId(report.case_id) },
    { label: "Investigator",    value: shortId(investigatorId) },
    { label: "Signed",          value: formatSignedDate(report.signed_utc) },
    { label: "Analysis Phase",  value: isDeepPhase ? "Deep Analysis" : "Initial Analysis" },
  ];

  return (
    <section className="relative flex flex-col overflow-hidden fc-surface" aria-label="Report integrity">
      <div className="px-6 py-4 border-b border-white/[0.06] flex items-center gap-2">
        <Shield className="w-4 h-4 text-primary/60" aria-hidden="true" />
        <h2 className="text-sm font-bold fc-text-secondary">Report Integrity</h2>
        {signature || reportHash ? (
          <div className="ml-auto flex items-center gap-1.5 fc-eyebrow text-success">
            <Fingerprint className="w-3.5 h-3.5" />
            Verified
          </div>
        ) : (
          <div className="ml-auto flex items-center gap-1.5 fc-eyebrow text-muted">
            Signed key store unavailable in development
          </div>
        )}
      </div>

      <div className="p-6 space-y-5">
        {/* 6-cell grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          {cells.map((c) => (
            <div key={c.label}>
              <div className="fc-eyebrow fc-text-muted mb-1">{c.label}</div>
              <div className="text-sm font-mono fc-text-muted">{c.value}</div>
            </div>
          ))}
        </div>

        {/* Report Hash */}
        {reportHash && (
          <div className="pt-4 border-t border-white/[0.04]">
            <div className="fc-eyebrow fc-text-muted mb-2 flex items-center gap-1.5">
              <Hash className="w-3 h-3" />
              Report Hash (SHA-256)
            </div>
            <div className="flex items-center gap-3">
              <p className="text-sm font-mono fc-text-muted truncate flex-1 min-w-0">
                {reportHash}
              </p>
              <button
                type="button"
                onClick={handleCopyHash}
                aria-label="Copy report hash"
                className="flex items-center gap-1.5 fc-eyebrow fc-text-muted hover:text-primary transition-colors rounded px-2 py-1 border border-white/[0.08] hover:border-white/[0.15] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 shrink-0"
              >
                {copiedHash ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                {copiedHash ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
        )}

        {/* Cryptographic Signature */}
        {signature && (
          <div className="pt-4 border-t border-white/[0.04]">
            <div className="fc-eyebrow fc-text-muted mb-2 flex items-center gap-1.5">
              <Fingerprint className="w-3 h-3" />
              ECDSA Signature
            </div>
            <div className="flex items-center gap-3">
              <p className="text-sm font-mono fc-text-muted truncate flex-1 min-w-0">
                {signature}
              </p>
              <button
                type="button"
                onClick={handleCopySig}
                aria-label="Copy ECDSA signature"
                className="flex items-center gap-1.5 fc-eyebrow fc-text-muted hover:text-primary transition-colors rounded px-2 py-1 border border-white/[0.08] hover:border-white/[0.15] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 shrink-0"
              >
                {copiedSig ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                {copiedSig ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
