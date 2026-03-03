# Developer Integration Guide

This document provides a technical overview of the **Forensic Council** frontend architecture to assist with backend integration.

## 1. Project Structure
The project follows a modular Next.js 15 (App Router) structure.

```
src/
├── app/                  # Application Routes (Next.js App Router)
│   ├── evidence/         # Evidence Intake Page (Upload & Simulation)
│   │   └── page.tsx      # Main logic for upload handling & agent simulation
│   ├── result/           # Analysis Result Page
│   │   └── page.tsx      # Displays report & local history
│   ├── layout.tsx        # Global Root Layout (Metadata & Fonts)
│   ├── page.tsx          # Landing Page (Hero Section)
│   └── globals.css       # Global Tailwind Styles
│
├── components/           # Reusable UI Components
│   └── ui/
│       └── AgentIcon.tsx # Dynamic icon renderer based on Agent Role
│
├── hooks/                # Custom React Hooks
│   ├── useForensicData.ts # Persistence (LocalStorage) & Data Validation
│   └── useSimulation.ts   # Agent Analysis Sequence Logic
│
├── lib/                  # Utilities & Constants
│   ├── constants.ts      # Agent Definitions & Thinking Phrases
│   ├── schemas.ts        # Zod Schemas for Type Validation
│   └── utils.ts          # Tailwind Class Utility (cn)
│
└── types/                # Global TypeScript Definitions
    └── index.ts          # Report, AgentResult, AgentDefinition interfaces
```

## 2. Key Dependencies
*   **Framework**: `next` (v16 Canary), `react` (v19)
*   **Styling**: `tailwindcss` (v4), `clsx`, `tailwind-merge`
*   **Animation**: `framer-motion` (Orchestration & UI transitions)
*   **Validation**: `zod` (Runtime schema validation)
*   **Icons**: `lucide-react`
*   **3D Elements**: `three`, `@react-three/fiber` (Ready for expansion)

## 3. Core Logic & Files
### `src/hooks/useForensicData.ts`
*   **Purpose**: Manages global state for `Current Report` and `History` using `localStorage`.
*   **Integration Point**:
    *   Currently mocks persistence via `localStorage`.
    *   **Backend TODO**: Replace `saveCurrentReport` and `addToHistory` with API POST requests to your database (e.g., `/api/reports`).
    *   **Validation**: Uses `validateFile` to enforce 50MB limits and MIME types.

### `src/hooks/useSimulation.ts`
*   **Purpose**: Controls the 3-second "Analysis" delay and dynamic "Thinking" text rotation.
*   **Integration Point**:
    *   Currently simulates async work with `setTimeout`.
    *   **Backend TODO**: Replace `setTimeout` callbacks with real WebSocket events or Server-Sent Events (SSE) if you want real-time agent feedback from a backend pipeline.

### `src/lib/constants.ts`
*   **Purpose**: Central source of truth for Agent personas (Name, Role, Description) and their "Thinking Phrases".
*   **Integration Point**:
    *   If your backend dynamically defines agents, fetch this configuration from an API endpoint (`GET /api/agents/config`) instead of hardcoding.

### `src/app/evidence/page.tsx`
*   **Purpose**: File upload and main simulation loop.
*   **Logic**:
    *   Validates file input.
    *   Triggers audio context (singleton reference).
    *   Orchestrates the UI state (`idle` -> `analyzing` -> `agents` -> `complete`).

### `src/app/result/page.tsx`
*   **Purpose**: Displays the final forensic report.
*   **Features**:
    *   Hydration-safe rendering (Client-side mount check).
    *   JSON Export (Client-side serialization).
    *   **Backend TODO**: Implement "PDF Export" by sending the Report ID to a backend generator endpoint.

## 4. Data Types (Interface Agreement)
Refer to `src/types/index.ts` for the exact shape of data expected by the frontend.
*   **`Report`**: The top-level object containing a summary and list of `AgentResult`.
*   **`AgentResult`**: Individual findings from specific agents.

## 5. Environment & scripts
*   `npm run build`: Production build (Static Output).
*   `npm run dev`: Local development server (Port 3000).
