# Component Guide

## Overview

Current frontend components live under `apps/web/src/components`. This guide is
intentionally structural: use the component source and tests as the API of record.

**Version:** v1.7.0  
**Last regenerated:** 2026-05-11 (from filesystem glob — do not edit by hand, re-run the glob)

## App Routes

| Route | File | Purpose |
|-------|------|---------|
| `/` | `apps/web/src/app/page.tsx` | Landing and investigation entry point |
| `/evidence` | `apps/web/src/app/evidence/page.tsx` | Evidence upload and live investigation workflow |
| `/result` | `apps/web/src/app/result/page.tsx` | Latest result view |
| `/result/[sessionId]` | `apps/web/src/app/result/[sessionId]/page.tsx` | Session-specific result view |
| `/session-expired` | `apps/web/src/app/session-expired/page.tsx` | Expired-session recovery |
| `/api/v1/[...path]` | `apps/web/src/app/api/v1/[...path]/route.ts` | Next.js backend proxy |
| `/api/auth/demo` | `apps/web/src/app/api/auth/demo/route.ts` | Server-side demo login route |

## Evidence Components

Located in `apps/web/src/components/evidence/`.

| Component | Purpose |
|-----------|---------|
| `AgentProgressDisplay.tsx` | Multi-agent progress display with per-agent status |
| `AgentProgressSkeleton.tsx` | Loading skeleton during agent progress |
| `AgentStatusCard.tsx` | Individual agent status card |
| `AgentStatusSummary.tsx` | Aggregated agent status summary |
| `ArbiterCard.tsx` | Council Arbiter status card |
| `ArbiterDeliberationOverlay.tsx` | Overlay shown during arbiter deliberation |
| `ErrorDisplay.tsx` | Evidence workflow error state |
| `ForensicTimeline.tsx` | Investigation timeline |
| `HITLCheckpointModal.tsx` | Human-in-the-loop decision modal |
| `QuotaMeter.tsx` | Quota usage display |
| `UploadModal.tsx` | Upload dialog |
| `UploadSuccessModal.tsx` | Successful upload confirmation |

Import these through `apps/web/src/components/evidence/index.ts` when possible.

## Result Components

Located in `apps/web/src/components/result/`.

| Component | Purpose |
|-----------|---------|
| `ActionDock.tsx` | Result actions (download, copy, etc.) |
| `AgentAnalysisTab.tsx` | Per-agent findings tab |
| `AgentFindingSubComponents.tsx` | Finding details and sub-sections |
| `ArcGauge.tsx` | Gauge visualization |
| `DeepModelTelemetry.tsx` | Deep-model runtime telemetry |
| `DegradationBanner.tsx` | Degraded-analysis indicator |
| `EvidenceThumbnail.tsx` | Evidence preview |
| `HistoryPanel.tsx` | Prior session/report history |
| `IntelligenceBrief.tsx` | Narrative summary |
| `ReportFooter.tsx` | Report footer |
| `ResultHeader.tsx` | Report identity and status header |
| `ResultLayout.tsx` | Result page layout shell |
| `ResultStateView.tsx` | Loading, empty, and error states |
| `TimelineTab.tsx` | Analysis timeline |

## UI Components

Located in `apps/web/src/components/ui/`.

| Component | Purpose |
|-----------|---------|
| `AgentFindingCard.tsx` | Shared finding card |
| `AgentIcon.tsx` | Agent icon resolver |
| `AgentsSection.tsx` | Agent overview section |
| `AnimatedNumber.tsx` | Animated numeric display |
| `Badge.tsx` | Status badge |
| `BrandLogo.tsx` | Product mark |
| `dialog.tsx` | Radix dialog wrapper |
| `ForensicErrorModal.tsx` | Error modal |
| `ForensicProgressOverlay.tsx` | Generic progress overlay |
| `GlassPanel.tsx` | Glass-style panel primitive |
| `GlobalFooter.tsx` | App footer |
| `GlobalNavbar.tsx` | App navigation |
| `HeroAuthActions.tsx` | Hero authentication actions |
| `HowWorksSection.tsx` | Workflow overview section |
| `LandingBackground.tsx` | Landing visual background |
| `LoadingOverlay.tsx` | Loading overlay |
| `QueryProvider.tsx` | React Query provider |
| `RouteExperience.tsx` | Route-level experience wrapper |
| `Toaster.tsx` | Toast container |

Import shared UI through `apps/web/src/components/ui/index.ts` when exported there.