import sys
import os
sys.path.insert(0, "/app")

from core.react_loop import ReActLoopEngine

class MockTool:
    def __init__(self, name):
        self.name = name
        self.description = ""

tools = [MockTool("gemini_deep_forensic")]
task = "Run Gemini deep forensic analysis: identify content type, extract all text, detect objects and weapons, identify interfaces, describe what is happening, cross-validate metadata"

best_tool = ReActLoopEngine._match_tool_to_task(task, tools)

if best_tool:
    print(f"MATCH FOUND: {best_tool.name}")
else:
    print("NO MATCH FOUND")

# Check overrides too
print(f"Overrides keys: {list(ReActLoopEngine._TASK_TOOL_OVERRIDES.keys())[:5]}")
print(f"Is 'gemini deep forensic analysis' in overrides? {'gemini deep forensic analysis' in ReActLoopEngine._TASK_TOOL_OVERRIDES}")
