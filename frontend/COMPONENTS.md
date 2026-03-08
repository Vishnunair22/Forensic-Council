# Component Guide

## Overview

This guide provides quick reference for all frontend components, their purposes, and usage examples.

## Table of Contents

- [Page Components](#page-components)
- [Evidence Components](#evidence-components)
- [UI Components](#ui-components)
- [Component Usage Examples](#component-usage-examples)

---

## Page Components

### Landing Page
**File:** `app/page.tsx`
**Purpose:** Main entry point for the application
**Key Features:**
- Project introduction
- Feature highlights
- File upload modal
- Navigation to evidence page

### Evidence Page
**File:** `app/evidence/page.tsx`
**Purpose:** Main investigation workflow orchestrator
**Key Features:**
- File upload and validation
- Real-time agent analysis display
- WebSocket integration
- HITL decision handling
- Navigation to results

### Results Page
**File:** `app/result/page.tsx`
**Purpose:** Display final forensic analysis report
**Key Features:**
- Report summary
- Agent findings
- Confidence scores
- Evidence export options

### Session Expired Page
**File:** `app/session-expired/page.tsx`
**Purpose:** Handle authentication timeout
**Key Features:**
- Timeout notification
- Re-authentication link
- Session recovery

---

## Evidence Components

These components are located in `components/evidence/` and are used on the evidence investigation page.

### HeaderSection

**File:** `components/evidence/HeaderSection.tsx`

**Purpose:** Displays page header with app branding and navigation

**Props:**
```typescript
interface HeaderSectionProps {
  status: string;                    // Current investigation status
  showBrowse: boolean;               // Show browse button
  onBrowseClick: () => void;        // Browse click handler
}
```

**Usage:**
```typescript
<HeaderSection
  status={status}
  showBrowse={showUploadForm}
  onBrowseClick={() => fileInputRef.current?.click()}
/>
```

**Features:**
- Logo that links to home (when not analyzing)
- Browse System button for file selection
- Status-aware interactions

---

### FileUploadSection

**File:** `components/evidence/FileUploadSection.tsx`

**Purpose:** Handles evidence file selection with drag-and-drop and preview

**Props:**
```typescript
interface FileUploadSectionProps {
  file: File | null;                           // Selected file
  isDragging: boolean;                         // Drag-over state
  isUploading: boolean;                        // Upload in progress
  validationError: string | null;              // Validation error
  onFileSelect: (file: File) => void;         // File selected
  onFileDrop: (file: File) => void;           // File dropped
  onDragEnter: () => void;                    // Drag enter
  onDragLeave: () => void;                    // Drag leave
  onUpload: (file: File) => void;             // Start upload
  onClear: () => void;                        // Clear selection
}
```

**Usage:**
```typescript
<FileUploadSection
  file={file}
  isDragging={isDragging}
  isUploading={isUploading}
  validationError={validationError}
  onFileSelect={handleFile}
  onFileDrop={handleFile}
  onDragEnter={() => setIsDragging(true)}
  onDragLeave={() => setIsDragging(false)}
  onUpload={triggerAnalysis}
  onClear={() => setFile(null)}
/>
```

**Features:**
- Drag-and-drop upload area
- File preview for images/videos
- Audio waveform animation
- File size validation
- Upload progress
- Clear and upload buttons

---

### AgentProgressDisplay

**File:** `components/evidence/AgentProgressDisplay.tsx`

**Purpose:** Shows real-time progress of forensic agents

**Props:**
```typescript
interface AgentProgressDisplayProps {
  completedAgents: AgentUpdate[];        // Completed agents
  activeAgent: AgentUpdate | null;       // Currently active agent
  progressText: string;                  // Progress description
  allAgentsDone: boolean;                // All agents done flag
}

interface AgentUpdate {
  agent_id: string;
  agent_name: string;
  message: string;
  status: "running" | "complete" | "error";
  confidence?: number;
  findings_count?: number;
  thinking?: string;
  error?: string | null;
}
```

**Usage:**
```typescript
<AgentProgressDisplay
  completedAgents={validCompletedAgents}
  activeAgent={activeAgent}
  progressText={progressText}
  allAgentsDone={allAgentsDone}
/>
```

**Features:**
- Active agent card with thinking
- Progress bar animation
- Completed agents list
- Findings count
- Overall progress text
- Loading indicator dots

---

### CompletionBanner

**File:** `components/evidence/CompletionBanner.tsx`

**Purpose:** Displays success message when analysis completes

**Props:**
```typescript
interface CompletionBannerProps {
  agentCount: number;                    // Total agents
  completedCount: number;                // Completed agents
  onViewResults: () => void;            // View report callback
  onAnalyzeNew: () => void;             // Analyze new callback
}
```

**Usage:**
```typescript
<CompletionBanner
  agentCount={validAgentsData.length}
  completedCount={validCompletedAgents.length}
  onViewResults={handleViewResults}
  onAnalyzeNew={handleAnalyzeNew}
/>
```

**Features:**
- Success icon animation
- Analysis summary
- Agent status grid
- View Report button
- Analyze New Evidence button
- Security disclaimer

---

### ErrorDisplay

**File:** `components/evidence/ErrorDisplay.tsx`

**Purpose:** Shows error messages with recovery options

**Props:**
```typescript
interface ErrorDisplayProps {
  message: string;                       // Error message
  onDismiss?: () => void;               // Dismiss callback
  onRetry?: () => void;                 // Retry callback
  showRetry?: boolean;                  // Show retry button
}
```

**Usage:**
```typescript
<ErrorDisplay
  message={errorMessage}
  onDismiss={() => resetSimulation()}
  onRetry={() => triggerAnalysis(file)}
  showRetry={!!file}
/>
```

**Features:**
- Error icon
- Detailed error message
- Try Again button (conditional)
- Dismiss button
- Motion animations

---

### HITLCheckpointModal

**File:** `components/evidence/HITLCheckpointModal.tsx`

**Purpose:** Handles human-in-the-loop decision points

**Props:**
```typescript
interface HITLCheckpoint {
  checkpoint_id: string;
  session_id: string;
  agent_id: string;
  agent_name: string;
  brief_text: string;
  decision_needed: string;
  created_at: string;
}

type HITLDecision = "APPROVE" | "REDIRECT" | "OVERRIDE" | "TERMINATE" | "ESCALATE";

interface HITLCheckpointModalProps {
  checkpoint: HITLCheckpoint | null;
  isOpen: boolean;
  isSubmitting: boolean;
  onDecision: (decision: HITLDecision, note?: string) => Promise<void>;
  onDismiss: () => void;
}
```

**Usage:**
```typescript
<HITLCheckpointModal
  checkpoint={hitlCheckpoint}
  isOpen={!!hitlCheckpoint}
  isSubmitting={isSubmittingHITL}
  onDecision={handleHITLDecision}
  onDismiss={dismissCheckpoint}
/>
```

**Features:**
- Finding summary
- Decision options (APPROVE, REDIRECT, OVERRIDE, ESCALATE)
- Notes field
- Error handling
- Async decision submission

---

## UI Components

### dialog.tsx

**Purpose:** Dialog/modal component wrapper

**Usage:**
```typescript
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";

<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Title</DialogTitle>
      <DialogDescription>Description</DialogDescription>
    </DialogHeader>
    {/* Content */}
    <DialogFooter>
      {/* Buttons */}
    </DialogFooter>
  </DialogContent>
</Dialog>
```

### AgentIcon.tsx

**Purpose:** Displays agent-specific icon

**Usage:**
```typescript
import { AgentIcon } from "@/components/ui/AgentIcon";

<AgentIcon agentId="Agent1" />
```

### AgentResponseText.tsx

**Purpose:** Formats and displays agent responses

**Usage:**
```typescript
import { AgentResponseText } from "@/components/ui/AgentResponseText";

<AgentResponseText
  text={agentMessage}
  agentId="Agent1"
/>
```

---

## Component Usage Examples

### Complete Evidence Page Setup

```typescript
"use client";

import { useState, useCallback } from "react";
import { AnimatePresence } from "framer-motion";
import {
  HeaderSection,
  FileUploadSection,
  AgentProgressDisplay,
  CompletionBanner,
  ErrorDisplay,
  HITLCheckpointModal,
} from "@/components/evidence";
import { useSimulation } from "@/hooks/useSimulation";

export default function EvidencePage() {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  
  const {
    status,
    agentUpdates,
    completedAgents,
    hitlCheckpoint,
    errorMessage,
    // ... other hooks
  } = useSimulation({
    playSound: () => {},
    onComplete: () => {},
  });

  return (
    <div className="min-h-screen bg-black text-white">
      <HeaderSection
        status={status}
        showBrowse={status === "idle"}
        onBrowseClick={() => {}}
      />
      
      <main>
        <AnimatePresence mode="wait">
          {status === "idle" && (
            <FileUploadSection
              file={file}
              isDragging={isDragging}
              isUploading={false}
              validationError={null}
              onFileSelect={setFile}
              onFileDrop={setFile}
              onDragEnter={() => setIsDragging(true)}
              onDragLeave={() => setIsDragging(false)}
              onUpload={() => {}}
              onClear={() => setFile(null)}
            />
          )}
          
          {status === "analyzing" && (
            <AgentProgressDisplay
              completedAgents={completedAgents}
              activeAgent={null}
              progressText="Analyzing..."
              allAgentsDone={false}
            />
          )}
          
          {status === "complete" && (
            <CompletionBanner
              agentCount={5}
              completedCount={5}
              onViewResults={() => {}}
              onAnalyzeNew={() => {}}
            />
          )}
          
          {errorMessage && (
            <ErrorDisplay
              message={errorMessage}
              onDismiss={() => {}}
              onRetry={() => {}}
            />
          )}
        </AnimatePresence>
      </main>

      <HITLCheckpointModal
        checkpoint={hitlCheckpoint}
        isOpen={!!hitlCheckpoint}
        isSubmitting={false}
        onDecision={async () => {}}
        onDismiss={() => {}}
      />
    </div>
  );
}
```

---

## Import Patterns

### From Evidence Components
```typescript
// Import individual components
import { HeaderSection } from "@/components/evidence/HeaderSection";
import { FileUploadSection } from "@/components/evidence/FileUploadSection";

// OR use index export
import {
  HeaderSection,
  FileUploadSection,
  AgentProgressDisplay,
  CompletionBanner,
  ErrorDisplay,
  HITLCheckpointModal,
} from "@/components/evidence";
```

### From UI Components
```typescript
import { AgentIcon } from "@/components/ui/AgentIcon";
import { AgentResponseText } from "@/components/ui/AgentResponseText";
import {
  Dialog,
  DialogContent,
  DialogHeader,
} from "@/components/ui/dialog";
```

---

## Component Best Practices

### Props Design
- Keep props specific and meaningful
- Use TypeScript interfaces for type safety
- Provide sensible defaults where possible
- Document all props with JSDoc

### Accessibility
- Add ARIA labels to interactive elements
- Use semantic HTML
- Ensure keyboard navigation
- Test color contrast

### Performance
- Memoize expensive computations with `useMemo`
- Use `useCallback` for event handlers
- Implement proper cleanup in `useEffect`
- Avoid unnecessary re-renders

### Styling
- Use Tailwind core utilities only
- Follow consistent spacing and sizing
- Use theme colors consistently
- Test responsive layouts

### Animation
- Use Framer Motion for smooth transitions
- Keep animations under 400ms for UI feedback
- Provide motion-safe alternatives
- Test on lower-end devices

---

## Troubleshooting

### Component Not Rendering
1. Check component is exported from index file
2. Verify import path is correct
3. Ensure props match interface
4. Check for console errors

### Styling Not Applied
1. Clear Next.js cache: `npm run build`
2. Check Tailwind class names
3. Verify CSS is loaded
4. Check CSS specificity

### Animation Not Working
1. Ensure Framer Motion is installed
2. Check AnimatePresence wraps target components
3. Verify animation properties are defined
4. Check for conflicting CSS transitions

---

## Contributing

When adding new components:

1. Create component in appropriate directory
2. Write clear JSDoc comments
3. Define prop interfaces
4. Add error handling
5. Include accessibility features
6. Write tests
7. Update this guide

For more details, see `ARCHITECTURE.md`
