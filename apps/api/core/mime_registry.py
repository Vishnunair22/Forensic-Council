"""
Centralized MIME type and file extension registry for Forensic Council.
"""


class MimeRegistry:
    """Registry for mapping agents to supported file types."""

    @staticmethod
    def get_supported_types(agent_name: str) -> list[str]:
        """Return list of MIME prefixes supported by the agent."""
        from core.file_type_policy import AGENT_FILE_CAPABILITIES
        name = agent_name.lower()
        for key, caps in AGENT_FILE_CAPABILITIES.items():
            if key.lower() in name or name == key.lower():
                return caps["mime_prefixes"]
        return []

    @staticmethod
    def get_supported_extensions(agent_name: str) -> list[str]:
        """Return list of file extensions supported by the agent."""
        from core.file_type_policy import AGENT_FILE_CAPABILITIES
        name = agent_name.lower()
        for key, caps in AGENT_FILE_CAPABILITIES.items():
            if key.lower() in name or name == key.lower():
                return caps["extensions"]
        return []

    @classmethod
    def is_supported(cls, agent_name: str, mime_type: str = "", file_path: str = "") -> bool:
        """Check if a file is supported by an agent."""
        from core.structured_logging import get_logger
        _log = get_logger(__name__)

        supported_types = cls.get_supported_types(agent_name)
        if "*" in supported_types:
            return True

        if mime_type:
            for t in supported_types:
                if mime_type.lower().startswith(t.lower()):
                    return True

        if file_path:
            exts = cls.get_supported_extensions(agent_name)
            if "*" in exts:
                return True
            file_lower = file_path.lower()
            if any(file_lower.endswith(ext) for ext in exts):
                return True

        _log.debug(
            "Agent support rejected",
            agent=agent_name,
            mime=mime_type,
            ext=file_path.split(".")[-1] if "." in file_path else "none",
            supported_prefixes=supported_types
        )
        return False

