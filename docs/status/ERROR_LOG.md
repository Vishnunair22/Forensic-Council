# Error Log & Resolutions

## Frontend React "AnimatePresence" Warning
**Error**: `index.tsx:165 You're attempting to animate multiple children within AnimatePresence, but its mode is set to "wait".`
**Error**: `Encountered two children with the same key, "".`
**Root Cause**: The Next.js frontend rendered both `FileUploadSection` and `ErrorDisplay` simultaneously because the condition tracking when to show them overlapped (e.g., when `status === "idle"` but `validationError` was set). Additionally, the elements passed into `AnimatePresence` lacked distinct `key` props.
**Resolution**:
- I made the components mutually exclusive so that `ErrorDisplay` only mounts if `!showUploadForm` and `!showAgentProgress` is true. `FileUploadSection` natively handles validation errors inside its own UI perfectly well.
- I added explicit `key` parameters (`key="upload-form"`, `key="agent-progress"`, `key="error-display"`) into the `page.tsx` render map and updated the TypeScript interfaces so the linter stops complaining about React Keys.

## Next.js Server "ERR_CONNECTION_REFUSED" Dropout
**Error**: 
```
favicon.ico:1 Failed to load resource: net::ERR_CONNECTION_REFUSED
api/v1/investigate:1 Failed to load resource: net::ERR_CONNECTION_REFUSED
__nextjs_original-stack-frames:1 Failed to load resource: net::ERR_CONNECTION_REFUSED
```
**Root Cause**: Given that `favicon.ico` and Next.js internal HMR bundles also threw a `Connection Refused` error at the exact same moment, the `Next.js` development server process running on port 3000 was temporarily dropped, crashed, or restarted. This was not a backend CORS or proxy issue, but rather the frontend server dying.
- No code changes are required for this specific backend endpoint. The API mapping in `next.config.ts` is 100% correct. If you continually experience the Next.js Dev server dropping out or crashing (possibly due to Windows file watcher OOM limits or HMR looping), running the production build (`npm run build` & `npm run start`) or explicitly restarting `npm run dev` addresses it.

## Real-Time Agent "Thinking" Updates Not Showing
**Error**: All agents displayed "Analyzing evidence..." instead of real-time `thinking` text for each analysis step.
**Root Cause**: The CustodyLogger payload broadcasted to the frontend stored the thought text in the `content` key, but `investigation.py` was looking for the `text` key (i.e. `content.get("text")`). Additionally, the `heartbeat()` loop had a 5.0s wait timeout, which caused fast tool executions to be completely missed by the UI.
**Resolution**:
- Updated `investigation.py` to correctly extract `content.get("content")` instead.
- Reduced the heartbeat loop timeout from 5.0 seconds to 1.0 seconds to ensure the UI catches fast internal state changes.
- Added a `last_thinking` deduplication check inside the `heartbeat()` loop to ensure it does not unconditionally overwrite the specific tool execution thoughts emitted asynchronously by the `CustodyLogger`.

## Deep Analysis Skipping Loading Phase
**Error**: After clicking the "Deep Analysis" button, the UI skipped the deep analysis loading phase and instantly rendered the "View Results" and "New Upload" buttons.
**Root Cause**: The UI relies on the `completedAgents` array. During Initial Analysis, all 5 agents populate this array. When "Deep Analysis" is clicked, this array was not cleared. Since it already had 5 entries, `allAgentsDone` evaluated to `true` instantly, causing `page.tsx` to mount the completion state immediately.
**Resolution**: 
- Created a `clearCompletedAgents()` function in `useSimulation.ts`.
- Subscribed to `clearCompletedAgents()` in `page.tsx` and called it exactly right when `handleDeepAnalysis` is executed, clearing out the old initial analysis findings so the loader properly re-mounts while the pipeline does its secondary check.
