# Forensic Council - Error Log

## March 11, 2026

### Error: TypeError in AgentProgressDisplay Component

**Error Message:**
```
TypeError: Cannot read properties of undefined (reading 'id')
    at AgentProgressDisplay.useEffect.revealInterval (AgentProgressDisplay.tsx:80:83)
```

**Stack Trace:**
```
at AgentProgressDisplay.useEffect.revealInterval (AgentProgressDisplay.tsx:80:83)
at basicStateReducer (react-dom-client.development.js:8257:45)
at updateReducerImpl (react-dom-client.development.js:8367:15)
at updateReducer (react-dom-client.development.js:8290:14)
at Object.useState (react-dom-client.development.js:28645:18)
at AgentProgressDisplay (AgentProgressDisplay.tsx:61:55)
```

**Root Cause:**
The error occurred in the `AgentProgressDisplay` component at line 74 where `visibleAgents[0].id` was being accessed without proper null checking. When `visibleAgents` could be an empty array, accessing `visibleAgents[0].id` would fail.

**Fix Applied:**
Changed line 74 in `frontend/src/components/evidence/AgentProgressDisplay.tsx` from:
```typescript
const firstVisibleId = hasVisibleAgents ? visibleAgents[0].id : null;
```
to:
```typescript
const firstVisibleAgent = visibleAgents[0];
const firstVisibleId = firstVisibleAgent ? firstVisibleAgent.id : null;
```

This ensures proper null checking before accessing the `id` property.

---

### Backend Issue: Image Agent Timeout (Agent1)

**Error Message:**
```
ERROR:api.routes.investigation:Agent1 timed out after 120s
```

**Root Cause:**
The agent timeout was hardcoded at 120 seconds which is too short for image analysis to complete.

**Fix Applied:**
Changed line 625 in `backend/api/routes/investigation.py` from:
```python
agent_timeout = min(120, pipeline.config.investigation_timeout * 0.6)
```
to:
```python
agent_timeout = min(300, pipeline.config.investigation_timeout * 0.6)
```

This increases the timeout to 300 seconds (5 minutes) for better agent completion.

---

### Backend Issue: Deep Analysis Failure

**Error Message:**
```
ERROR:api.routes.investigation:Deep pass failed for Agent3: float() argument must be a string or a real number, not 'NoneType'
```

**Root Cause:**
The calibration layer was receiving a None value for the confidence score and attempting to use it in a math operation.

**Fix Applied:**
Added a None check in `backend/core/calibration.py` before the sigmoid transformation:
```python
if raw_score is None:
    raw_score = 0.5  # Default to neutral confidence
```

---

### Backend Issue: Skipped Agent Message Format

**Issue:**
Skipped agents showed a generic message.

**Fix Applied:**
Changed line 643 in `backend/api/routes/investigation.py` from:
```python
clean_text = f"{agent_name} cannot analyze this file type ({mime})."
```
to:
```python
clean_text = f"{agent_name} does not support {base_name}. {agent_name} skipped forensic analysis."
```

---

### Known Issues to Investigate Further

1. **Metadata Agent "device unknown"**: When EXIF data doesn't contain device information, the metadata agent reports "unknown device". This is expected behavior for files without proper EXIF data.

2. **View Results / Arbiter not loading**: Investigation timed out after 600s according to logs - the report was not generated due to the overall timeout.

3. **Deep Analysis showing initial findings**: Due to the investigation timeout, deep analysis results may not be available.

**Additional Console Logs (Informational):**
```
[WebSocket] Received update, adding to queue: Object
[Simulation] Processing update from queue: Object
[WebSocket] Connection closed: 1005
```

These WebSocket messages are normal simulation/connection events and do not indicate errors.
