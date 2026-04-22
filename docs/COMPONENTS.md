# Component Guide

## Overview

Quick reference for all frontend components, their purposes, and usage examples.

**Version:** v1.4.0

## Table of Contents

- [Page Components](#page-components)
- [Evidence Components](#evidence-components)
- [UI Components](#ui-components)
- [Lightswind Components](#lightswind-components)
- [Dev Components](#dev-components)
- [Import Patterns](#import-patterns)

---

## Page Components

### Landing Page
**File:** `app/page.tsx`
**Purpose:** Main entry point — hero, how-it-works, agent showcase, example report, file upload modals.

### Evidence Page
**File:** `app/evidence/page.tsx`
**Purpose:** Investigation workflow orchestrator. Handles file upload, WebSocket agent stream, HITL decisions, deep analysis, and arbiter overlay.

### Result Page
**File:** `app/result/page.tsx`
**Purpose:** Signed forensic report display — per-agent findings, confidence scores, verdict, cryptographic proof, chain of custody, export.

### Session Expired Page
**File:** `app/session-expired/page.tsx`
**Purpose:** Session timeout recovery with re-authentication.

### 404 Page
**File:** `app/not-found.tsx`
**Purpose:** Global not-found handler.

---

## Evidence Components

Located in `components/evidence/`.

### HeaderSection
**File:** `components/evidence/HeaderSection.tsx`
**Props:**
```typescript
interface HeaderSectionProps {
  status: string;
  showBrowse: boolean;
  onBrowseClick: () => void;
}
```
Logo nav (keyboard-accessible), Browse System button, status-aware interactions.

### FileUploadSection
**File:** `components/evidence/FileUploadSection.tsx`
**Props:**
```typescript
interface FileUploadSectionProps {
  file: File | null;
  isDragging: boolean;
  isUploading: boolean;
  validationError: string | null;
  onFileSelect: (file: File) => void;
  onFileDrop: (file: File) => void;
  onDragEnter: () => void;
  onDragLeave: () => void;
  onUpload: (file: File) => void;
  onClear: () => void;
}
```
Drag-and-drop upload area with file preview for images/videos/audio. MIME validation, size check (50 MB max).

### AgentProgressDisplay
**File:** `components/evidence/AgentProgressDisplay.tsx`

The main analysis view. Renders a 3×2 grid of glass agent cards with live thinking text, tool progress bars, staggered reveal animation, decision buttons (Compile Ledger / Deep Scan Protocol), skipped-agent accordion, and animated Three.js wave background.

**Key internals:**
- `LiveThinkingText` — debounced text display with animated dots and trailing previous-thought
- `humaniseThinking()` — translates raw backend task strings into user-friendly action sentences with emoji prefixes
- Agent status determination: `waiting` → `checking` → `running` → `complete`/`unsupported`/`error`

**Props:**
```typescript
interface AgentProgressDisplayProps {
  agentUpdates: Record<string, { status: string; thinking: string; tools_done?: number; tools_total?: number }>;
  completedAgents: AgentUpdate[];
  progressText: string;
  allAgentsDone: boolean;
  phase: "initial" | "deep";
  awaitingDecision: boolean;
  pipelineStatus: string;
  pipelineMessage?: string;
  onAcceptAnalysis: () => void;
  onDeepAnalysis: () => void;
  onNewUpload: () => void;
  onViewResults: () => void;
  playSound?: (type: SoundType) => void;
  isNavigating?: boolean;
}
```

### ErrorDisplay
**File:** `components/evidence/ErrorDisplay.tsx`
**Props:**
```typescript
interface ErrorDisplayProps {
  message: string;
  onRetry?: () => void;
  showRetry?: boolean;
}
```
Error state with retry button.

### HITLCheckpointModal
**File:** `components/evidence/HITLCheckpointModal.tsx`
**Props:**
```typescript
interface HITLCheckpointModalProps {
  checkpoint: HITLCheckpoint | null;
  isOpen: boolean;
  isSubmitting: boolean;
  onDecision: (decision: HITLDecision, note?: string) => Promise<void>;
  onDismiss: () => void;
}
```
Accessible modal for human review decisions: APPROVE, REDIRECT, OVERRIDE, TERMINATE, ESCALATE.

---

## UI Components

Located in `components/ui/`.

### AgentIcon
**File:** `components/ui/AgentIcon.tsx`
Resolves per-agent Lucide icon by role string (e.g. "Image Integrity" → Shield, "Audio" → Mic2).

### AgentResponseText
**File:** `components/ui/AgentResponseText.tsx`
Expandable text display with markdown stripping and character limit truncation.

### GlobalFooter
**File:** `components/ui/GlobalFooter.tsx`
Academic disclaimer footer rendered on all pages via layout.

### HistoryDrawer
**File:** `components/ui/HistoryDrawer.tsx`
Sidebar drawer showing session history from localStorage. Per-item delete, clear-all, verdict badges.

### PageTransition
**File:** `components/ui/PageTransition.tsx`
Wraps page content in smooth fade-up entrance animation. Exports `PageTransition`, `StaggerIn`, `StaggerChild`.

### SurfaceCard
**File:** `components/ui/SurfaceCard.tsx`
Simple wrapper component applying `surface-panel` glass styling.

### dialog.tsx
**File:** `components/ui/dialog.tsx`
Radix UI dialog primitive re-exported: `Dialog`, `DialogContent`, `DialogHeader`, `DialogFooter`, `DialogTitle`, `DialogDescription`, `DialogClose`.

---

## Lightswind Components

Located in `components/lightswind/`.

### Badge
**File:** `components/lightswind/badge.tsx`
Status badge with variants (`default`, `secondary`, `destructive`, `outline`, `success`, `warning`, `info`), sizes, shapes, optional colored dot.

### AnimatedWave
**File:** `components/lightswind/animated-wave.tsx`
Three.js animated wireframe wave background. Accepts speed, amplitude, opacity, wave color, mouse interaction, quality settings.

---

## Import Patterns

### Evidence Components (barrel export)
```typescript
import {
  HeaderSection,
  FileUploadSection,
  AgentProgressDisplay,
  ErrorDisplay,
  HITLCheckpointModal,
} from "@/components/evidence";
```

### UI Components (barrel export)
```typescript
import {
  AgentIcon,
  AgentResponseText,
  GlobalFooter,
  HistoryDrawer,
  PageTransition,
  SurfaceCard,
  Dialog,
  DialogContent,
} from "@/components/ui";
```

