"""
Forensic Context Utilities
==========================

Shared logic for aggregating forensic tool context across multiple agents.
Eliminates code duplication and ensures consistent forensic visibility.
"""

from typing import Any

def aggregate_tool_context(tool_context: dict[str, Any], agent_id: str = "") -> dict[str, Any]:
    """
    Collect all successful tool results from an agent's context.
    
    This provides a unified forensic narrative for the AI, ensuring that
    signals from one tool are visible to others.
    
    Args:
        tool_context: The raw _tool_context dictionary from an agent.
        agent_id: Optional agent ID to handle agent-specific summarization.
        
    Returns:
        A dictionary mapping tool names to their successful findings.
    """
    findings = {}
    for tool_name, result in tool_context.items():
        if not isinstance(result, dict):
            continue
        if result.get("available") is False:
            continue
        
        # Extract high-value forensic keys for Gemini
        # Filter out large raw data (detections, full artifacts, etc.)
        findings[tool_name] = {
            k: v
            for k, v in result.items()
            if k not in ("detections", "artifact", "error", "box", "frames", "audio_segments")
        }

        # Agent-specific enhancements
        if tool_name == "object_detection" and "detections" in result:
            findings[tool_name]["detections_summary"] = [
                {
                    "class": d.get("class_name") or d.get("label"),
                    "confidence": d.get("confidence"),
                    "box": d.get("box", {}),
                }
                for d in result.get("detections", [])[:20]
            ]
        
        if tool_name == "extract_text_from_image" and "extracted_text" in result:
             # Limit lines of text to prevent context saturation
             findings[tool_name]["text_sample"] = result["extracted_text"][:30]

    return findings
