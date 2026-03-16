# Frontend Architecture Documentation

## Project Structure Overview

```
frontend/
├── src/
│   ├── app/                    # Next.js app directory
│   │   ├── api/               # API routes and auth handlers
│   │   ├── evidence/          # Evidence investigation page
│   │   ├── result/            # Results display page
│   │   ├── session-expired/   # Session expiration page
│   │   ├── layout.tsx         # Root layout
│   │   ├── page.tsx           # Landing page
│   │   └── globals.css        # Global styles
│   │
│   ├── components/            # Reusable React components
│   │   ├── evidence/          # Evidence page components
│   │   │   ├── HeaderSection.tsx         # Page header with navigation
│   │   │   ├── FileUploadSection.tsx     # File upload form with drag-drop
│   │   │   ├── AgentProgressDisplay.tsx  # Agent analysis progress display
│   │   │   ├── CompletionBanner.tsx      # Analysis completion banner
│   │   │   ├── ErrorDisplay.tsx          # Error message display
│   │   │   ├── HITLCheckpointModal.tsx   # Human-in-the-loop modal
│   │   │   └── index.ts                  # Component exports
│   │   └── ui/                # UI components
│   │       ├── dialog.tsx             # Dialog/modal component
│   │       ├── AgentIcon.tsx          # Agent icon display
│   │       ├── AgentResponseText.tsx  # Formatted agent response
│   │       ├── GlobalFooter.tsx       # Global academic disclaimer footer
│   │       └── PageTransition.tsx     # Smooth page fade-up transition wrapper
│   │
│   ├── DevErrorOverlay.tsx    # Dev-only error boundary (stripped in prod)
│   │
│   ├── hooks/                 # Custom React hooks
│   │   ├── useForensicData.ts    # Forensic data management hook
│   │   ├── useSimulation.ts      # Investigation simulation hook
│   │   └── useSound.ts           # Sound effects hook
│   │
│   ├── lib/                   # Utility functions
│   │   ├── api.ts            # Backend API client
│   │   ├── constants.ts       # App constants and configurations
│   │   ├── schemas.ts         # Data validation schemas
│   │   └── utils.ts           # Utility functions
│   │
│   ├── types/                 # TypeScript type definitions
│   │   ├── index.ts          # Main types
│   │   └── global.d.ts        # Global type declarations
│   │
│   └── (tests live in tests/frontend/ at project root)
│
├── public/                    # Static assets
├── package.json               # Dependencies and scripts
├── tsconfig.json             # TypeScript configuration
├── next.config.ts            # Next.js configuration
└── jest.config.ts            # Jest testing configuration
```

## Component Hierarchy

### Page Structure

#### Landing Page (`/page.tsx`)
- Main entry point for the application
- Displays introduction and project information
- File upload modal for quick analysis start
- Navigation to evidence page
- Contains three inline helper components (not separate files): `MicroscopeScanner` (animated SVG hero), `EnvelopeCTA` (animated envelope call-to-action), `GlassCard` (glassmorphism card wrapper)

#### Evidence Page (`/evidence/page.tsx`)
- Main investigation workflow orchestrator
- Manages overall state and routing
- Coordinates all sub-components

**Sub-Components:**
```
EvidencePage
├── HeaderSection
├── FileUploadSection (when idle)
├── AgentProgressDisplay (while analyzing)
│   └── AgentUpdate cards
├── CompletionBanner (when complete)
├── ErrorDisplay (on error)
└── HITLCheckpointModal (when checkpoint exists)
```

#### Results Page (`/result/page.tsx`)
- Displays final forensic report
- Shows agent findings and conclusions
- Evidence handling recommendations

#### Session Expired Page (`/session-expired/page.tsx`)
- Handles authentication timeout
- Provides re-authentication option

### Component Purposes

#### **HeaderSection**
**Location:** `components/evidence/HeaderSection.tsx`

**Purpose:** Consistent header across pages with app branding and navigation

**Props:**
- `status: string` - Current investigation status
- `showBrowse: boolean` - Whether to show browse button
- `onBrowseClick: () => void` - Callback for browse button

**Features:**
- Clickable logo to return to home (when not analyzing)
- Browse System button for file selection
- Responsive design

---

#### **FileUploadSection**
**Location:** `components/evidence/FileUploadSection.tsx`

**Purpose:** Handles evidence file upload with drag-and-drop support

**Props:**
- `file: File | null` - Currently selected file
- `isDragging: boolean` - Drag-over state
- `isUploading: boolean` - Upload in progress
- `validationError: string | null` - Validation error message
- `onFileSelect: (file: File) => void` - File selected callback
- `onFileDrop: (file: File) => void` - File dropped callback
- `onDragEnter/Leave: () => void` - Drag handlers
- `onUpload: (file: File) => void` - Upload start callback
- `onClear: () => void` - Clear file callback

**Features:**
- Drag-and-drop upload area
- File preview for images/videos
- Audio waveform animation
- File size and type validation
- Upload progress indication
- Clear and upload buttons

---

#### **AgentProgressDisplay**
**Location:** `components/evidence/AgentProgressDisplay.tsx`

**Purpose:** Shows real-time progress of forensic agents analyzing evidence

**Props:**
- `completedAgents: AgentUpdate[]` - List of completed agents
- `activeAgent: AgentUpdate | null` - Currently active agent
- `progressText: string` - Progress description
- `allAgentsDone: boolean` - All agents completed flag

**Features:**
- Active agent card with thinking message
- Progress bar animation
- Completed agents list with findings count
- Overall progress indicator
- Animated loading states

---

#### **CompletionBanner**
**Location:** `components/evidence/CompletionBanner.tsx`

**Purpose:** Displays success message when analysis completes

**Props:**
- `agentCount: number` - Total agents deployed
- `completedCount: number` - Agents that completed
- `onViewResults: () => void` - View report callback
- `onAnalyzeNew: () => void` - Analyze new evidence callback

**Features:**
- Success icon animation
- Summary of analysis
- Agent completion status
- View Report button
- Analyze New Evidence button
- Security disclaimer

---

#### **ErrorDisplay**
**Location:** `components/evidence/ErrorDisplay.tsx`

**Purpose:** Shows error messages with recovery options

**Props:**
- `message: string` - Error message
- `onDismiss?: () => void` - Dismiss callback
- `onRetry?: () => void` - Retry callback
- `showRetry?: boolean` - Show retry button

**Features:**
- Error icon and title
- Detailed error message
- Try Again button (if applicable)
- Dismiss button
- Motion animations

---

#### **HITLCheckpointModal**
**Location:** `components/evidence/HITLCheckpointModal.tsx`

**Purpose:** Handles human-in-the-loop decision points during analysis

**Props:**
- `checkpoint: HITLCheckpoint | null` - Checkpoint data
- `isOpen: boolean` - Modal open state
- `isSubmitting: boolean` - Decision submission in progress
- `onDecision: (decision, note?) => Promise<void>` - Decision callback
- `onDismiss: () => void` - Close modal callback

**Features:**
- Finding summary display
- Action required description
- 4 decision options with descriptions:
  - APPROVE: Accept finding
  - REDIRECT: Send to different agent
  - OVERRIDE: Reject and provide alternate
  - ESCALATE: Flag for senior review
- Optional notes field
- Error handling and validation

---

### UI Components

#### **dialog.tsx**
- Radix UI Dialog component wrapper
- Used for modals and popups
- Accessible keyboard navigation

#### **AgentIcon.tsx**
- Displays agent-specific icon
- Color-coded by agent type

#### **AgentResponseText.tsx**
- Formats and displays agent responses
- Syntax highlighting for findings
- Responsive text rendering

---

## Data Flow

### Investigation Workflow

```
User selects file
    ↓
FileUploadSection validates & displays preview
    ↓
User clicks "Analyze"
    ↓
triggerAnalysis() starts investigation
    ↓
Backend creates session
    ↓
WebSocket connection established
    ↓
AgentProgressDisplay shows updates
    ↓
Real-time agent updates received via WS
    ↓
HITL checkpoint (optional)
    ↓
All agents complete
    ↓
CompletionBanner displayed
    ↓
User views results
```

### State Management

**Page-level state** (`evidence/page.tsx`):
- `file`: Selected file
- `isDragging`: Drag state
- `validationError`: Validation error
- `isUploading`: Upload in progress
- `isSubmittingHITL`: HITL decision submission

**Hook-based state** (`useSimulation`):
- `status`: Analysis status
- `agentUpdates`: Real-time agent updates
- `completedAgents`: Finished agents
- `hitlCheckpoint`: Current checkpoint
- `errorMessage`: Error messages

**Session storage**:
- `forensic_session_id`: Current investigation ID
- `forensic_investigator_id`: Investigator ID
- `forensic_case_id`: Case ID
- `forensic_file_name`: Uploaded file name

---

## Component Communication

### Parent → Child (Props)
- Page passes status, agent data to display components
- Components receive handlers as callbacks

### Child → Parent (Callbacks)
- Upload section calls `onUpload()` when ready
- Completion banner calls `onViewResults()`
- HITL modal calls `onDecision()`

### External Communication
- WebSocket hooks (`useSimulation`) manage backend updates
- API module (`lib/api.ts`) handles server calls

---

## Styling

### Tailwind CSS
- All components use Tailwind core utilities
- Custom color scheme:
  - Primary: Emerald (emerald-*)
  - Secondary: Cyan (cyan-*)
  - Accent: Slate (slate-*)
  - Warning: Amber (amber-*)
  - Error: Red (red-*)

### Motion & Animation
- Framer Motion for smooth transitions
- Page transitions with AnimatePresence
- Loading spinners and pulse animations
- Staggered component entry

---

## Testing

### Test Files
All tests live in `tests/frontend/` at the **project root** (not inside `frontend/`):
- `tests/frontend/unit/lib/api.test.ts` — API client + token management
- `tests/frontend/unit/hooks/useForensicData.test.ts` — Hook + mapReportDtoToReport
- `tests/frontend/unit/components/components.test.tsx` — Component rendering
- `tests/frontend/accessibility/accessibility.test.tsx` — WCAG 2.1 AA
- `tests/frontend/integration/page_flows.test.tsx` — Session flow
- `tests/frontend/e2e/websocket_flow.test.ts` — WebSocket lifecycle

### Running Tests
```bash
# From frontend/ directory:
npm test -- --watchAll=false   # One-shot (CI)
npm test                       # Watch mode
npm run test:coverage          # With coverage
```

---

## Development Guidelines

### Adding New Components

1. **Create component file** in appropriate directory
2. **Define interfaces** for props
3. **Add JSDoc comments** with purpose and props
4. **Export from index.ts** if part of a collection
5. **Use Tailwind** for styling
6. **Add animations** with Framer Motion
7. **Write tests** for logic

### File Naming
- Components: PascalCase (`HeaderSection.tsx`)
- Hooks: camelCase with "use" prefix (`useForensicData.ts`)
- Utils: camelCase (`schemas.ts`)
- Pages: lowercase (`page.tsx`)

### Component Template

```typescript
/**
 * ComponentName
 * =============
 * 
 * Brief description of what this component does.
 */

import { ReactNode } from "react";

interface ComponentNameProps {
  /** Description of prop */
  prop1: string;
  /** Description of callback */
  onAction: () => void;
}

export function ComponentName({ prop1, onAction }: ComponentNameProps) {
  return (
    <div className="...">
      {/* Component content */}
    </div>
  );
}
```

---

## Performance Optimization

### Memoization
- File preview URL: `useMemo` to prevent recreation
- Callbacks: `useCallback` for event handlers

### Code Splitting
- Page components loaded separately
- Feature-specific components bundled together

### Resource Management
- Blob URLs revoked on cleanup
- Event listeners removed on unmount
- WebSocket connections properly closed

---

## Accessibility

### ARIA Labels
- File input: `aria-label="Upload evidence file"`
- Buttons: Descriptive labels
- Modals: Dialog semantics

### Keyboard Navigation
- All buttons accessible via Tab
- Modal forms navigable via keyboard
- Focus management in modals

### Color Contrast
- All text meets WCAG AA standards
- Icons supplemented with text labels

---

## Troubleshooting

### Components Not Rendering
- Check imports from index files
- Verify prop types match interfaces
- Review component export statements

### Animation Issues
- Ensure Framer Motion is installed
- Check AnimatePresence wraps components
- Verify exit animations are defined

### Styling Problems
- Clear Tailwind cache: `npm run build`
- Verify class names are valid
- Check CSS specificity

---

## Future Improvements

- [ ] Server-side rendering optimizations
- [ ] Component storybook setup
- [ ] More comprehensive test coverage
- [ ] Accessibility audit and improvements
- [ ] Performance monitoring
- [ ] Error boundary implementation
- [ ] Loading skeleton screens
- [ ] Advanced filtering/search UI
