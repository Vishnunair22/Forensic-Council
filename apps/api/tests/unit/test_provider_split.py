"""Tests that the default provider chains keep Gemini reserved for vision only."""

from core.config import Settings


def test_default_chains_keep_gemini_for_vision_only():
    s = Settings()
    assert s.vision_provider_chain.split(",")[0] == "gemini"
    assert s.text_provider_chain.split(",")[0] == "groq"
