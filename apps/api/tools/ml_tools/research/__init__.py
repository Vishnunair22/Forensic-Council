"""
Research / Unregistered ML Tools
==================================

Tools in this directory are complete implementations that have NOT been
registered in core/tool_registry.py or the ml_subprocess warmup list.

They are preserved here because:
  - The implementation is valid and may be registered in a future release
  - The tool requires additional licensing review before production use
  - The tool is experimental and has not been validated on the forensic corpus

To promote a tool from here to the active set:
  1. Move the file to tools/ml_tools/
  2. Add an entry to core/ml_subprocess._WARMUP_SCRIPTS
  3. Register it in core/tool_registry.py with a TOOL_TIMEOUTS entry
  4. Wire it into the appropriate agent handler

Do NOT import from this package in production code.
"""
