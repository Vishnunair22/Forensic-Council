"""
Centralized MIME type and file extension registry for Forensic Council.
"""



class MimeRegistry:
    """ Registry for mapping agents to supported file types. """

    @staticmethod
    def get_supported_types(agent_name: str) -> list[str]:
        """ Return list of MIME prefixes supported by the agent. """
        name = agent_name.lower()
        if "agent1" in name or "imageintegrity" in name:
            return ["image/"]
        if "agent2" in name or "audioforensics" in name:
            return ["audio/", "video/"]
        if "agent3" in name or "objectdetection" in name:
            # Audit Fix: Agent 3 handlers support video frame extraction
            return ["image/", "video/"]
        if "agent4" in name or "temporalvideo" in name:
            return ["video/"]
        if "agent5" in name or "metadatacontext" in name:
            return ["*"] # Supports all
        return ["*"]

    @staticmethod
    def get_supported_extensions(agent_name: str) -> list[str]:
        """ Return list of file extensions supported by the agent. """
        name = agent_name.lower()

        audio_exts = [".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a", ".wma", ".opus", ".amr", ".aiff"]
        video_exts = [".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".m4v", ".3gp", ".ts", ".ogv"]
        image_exts = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif", ".dng", ".avif", ".raw"]

        if "agent1" in name or "imageintegrity" in name:
            return image_exts
        if "agent2" in name or "audioforensics" in name:
            return audio_exts + video_exts
        if "agent3" in name or "objectdetection" in name:
            return image_exts + video_exts
        if "agent4" in name or "temporalvideo" in name:
            return video_exts
        return ["*"]

    @classmethod
    def is_supported(cls, agent_name: str, mime_type: str = "", file_path: str = "") -> bool:
        """ Check if a file is supported by an agent. """
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

        return False
