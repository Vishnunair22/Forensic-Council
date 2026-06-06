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

    @staticmethod
    def get_full_mimes(agent_name: str) -> list[str]:
        """Return list of exact (non-prefix) MIME types supported by the agent.

        Some agents support a MIME type that has no useful prefix grouping
        (e.g. application/pdf for Agent5). These are declared in `full_mimes`
        and matched exactly rather than by prefix.
        """
        from core.file_type_policy import AGENT_FILE_CAPABILITIES
        name = agent_name.lower()
        for key, caps in AGENT_FILE_CAPABILITIES.items():
            if key.lower() in name or name == key.lower():
                return caps.get("full_mimes", [])
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
            mime_lower = mime_type.lower()
            for t in supported_types:
                if mime_lower.startswith(t.lower()):
                    return True
            # Exact-match MIME types (e.g. application/pdf for Agent5) — these
            # have no useful prefix so they are declared in `full_mimes` and
            # must be matched exactly. Without this, PDF support depended solely
            # on the .pdf path extension surviving downstream (latent bug).
            full_mimes = cls.get_full_mimes(agent_name)
            if mime_lower in (m.lower() for m in full_mimes):
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

