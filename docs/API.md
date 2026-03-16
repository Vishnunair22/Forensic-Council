# Forensic Council API Reference

This document outlines the REST endpoints and WebSocket protocols exposed by the FastAPI backend (`http://localhost:8000/api/v1`). 

For complete Data Transfer Objects (DTOs), refer to `SCHEMAS.md`.

## REST Endpoints

### 1. Initiate Investigation
Uploads digital evidence and initiates the multi-agent ReAct pipeline.

*   **URL:** `/investigate`
*   **Method:** `POST`
*   **Content-Type:** `multipart/form-data`
*   **Parameters:**
    *   `file` (File): The evidence fragment (max 50MB).
    *   `case_id` (String): The client-provided case identifier (e.g. `CASE-1234`).
    *   `investigator_id` (String): The ID of the authenticated user.

*   **Response (200 OK):**
    ```json
    {
      "session_id": "uuid-v4-string",
      "case_id": "CASE-1234",
      "status": "initiating",
      "message": "Investigation started successfully."
    }
    ```
*   **Errors:**
    *   `400 Bad Request`: File size exceeds limits.
    *   `415 Unsupported Media Type`: File format not supported.
    *   `429 Too Many Requests`: Rate limit per `investigator_id` exceeded.

### 2. Fetch Pending HITL Checkpoints
Retrieves Human-In-The-Loop checkpoints requiring manual intervention.

*   **URL:** `/sessions/{session_id}/checkpoints`
*   **Method:** `GET`
*   **Response (200 OK):** Returns a list of `HITLCheckpoint` schemas. Returns `[]` if none.

### 3. Submit HITL Decision
Resolves a paused checkpoint.

*   **URL:** `/hitl/decision`
*   **Method:** `POST`
*   **Content-Type:** `application/json`
*   **Body:**
    ```json
    {
      "session_id": "...",
      "checkpoint_id": "...",
      "agent_id": "...",
      "decision": "APPROVE" // or "REDIRECT", "TERMINATE"
    }
    ```
*   **Response (200 OK):** Blank success message indicating the agent pipeline has resumed.

### 4. Resume Investigation (Accept or Deep Analysis)

After initial analysis completes, the client must POST to resume the pipeline.

*   **URL:** `/{session_id}/resume`
*   **Method:** `POST`
*   **Body:** `{"deep_analysis": false}` — `false` for Accept Analysis, `true` for Deep Analysis
*   **Response:** `{"status": "resumed"}`

### 5. Fetch Final Report
Polls the investigation state. Once the Arbiter concludes, it returns the cryptographically signed DTO.

*   **URL:** `/sessions/{session_id}/report`
*   **Method:** `GET`
*   **Responses:**
    *   `202 Accepted`: Analysis still in progress.
    *   `200 OK`: Returns the `ReportDTO` schema.
    *   `404 Not Found`: Session ID invalid or expired from Redis.

---

## WebSocket Protocol

The frontend receives real-time streams of agent cognition via WebSockets.

*   **URL:** `ws://localhost:8000/api/v1/sessions/{session_id}/live`

### Event Payloads

The primary message payload structure (`BriefUpdate` schema):
```json
{
  "type": "AGENT_UPDATE",
  "session_id": "uuid-v4-string",
  "agent_id": "Agent1",
  "agent_name": "Image Integrity Expert",
  "message": "Analyzing EXIF metadata block...",
  "data": {
    "status": "deliberating",
    "thinking": "Extracting structural hashes..."
  }
}
```

### Event Types
1.  **`AGENT_UPDATE`**: An agent is actively working (ReAct internal chain). `data` contains status and current thought.
2.  **`AGENT_COMPLETE`**: A single agent finished its assignment. `data` contains its final confidence score.
3.  **`HITL_CHECKPOINT`**: An agent has paused and is requesting explicit manual override. `data` contains the `checkpoint_id`.
4.  **`PIPELINE_COMPLETE`**: The Arbiter finished synthesizing and the report is signed. Connection will sever shortly after.
5.  **`ERROR`**: Emitted upon fatal pipeline crash. Connection terminates.
