"""Unit tests for the by-hash visual-context TTL gate (_is_top_tier_context).

Only a genuinely high-quality authoritative Gemini read earns the 24h cross-session
cache; weaker reads get a short TTL so Gemini is re-attempted instead of a mediocre
read being locked in for a day. Duck-typed via SimpleNamespace so the tests exercise
the gate logic without constructing the full nested VisualContext pydantic model.
"""
import os
from types import SimpleNamespace

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.visual_context_store import _TOP_TIER_MIN_CONFIDENCE, _is_top_tier_context


def _ctx(**kw):
    base = dict(
        external_llm_used=True,
        source="llm_assisted",
        confidence=0.9,
        scene_description="A studio photograph of a pistol.",
        file_type_assessment="photograph",
        extracted_text=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_top_tier_gemini_read_qualifies():
    assert _is_top_tier_context(_ctx()) is True


def test_local_ensemble_fallback_rejected():
    # The GAN-face trap: a local read must never get the 24h TTL.
    assert _is_top_tier_context(_ctx(external_llm_used=False, source="local_ensemble")) is False


def test_external_llm_flag_false_rejected():
    assert _is_top_tier_context(_ctx(external_llm_used=False)) is False


def test_source_not_llm_assisted_rejected():
    # Defensive: external_llm_used True but source says local → reject.
    assert _is_top_tier_context(_ctx(source="local_ensemble")) is False


def test_low_confidence_rejected():
    assert _is_top_tier_context(_ctx(confidence=0.5)) is False


def test_confidence_at_threshold_qualifies():
    assert _is_top_tier_context(_ctx(confidence=_TOP_TIER_MIN_CONFIDENCE)) is True


def test_contentless_read_rejected():
    assert _is_top_tier_context(
        _ctx(scene_description="", file_type_assessment="", extracted_text=[])
    ) is False


def test_non_image_cannot_determine_with_description_qualifies():
    # Audio/video/document contexts legitimately carry CANNOT_DETERMINE (verdict is
    # deferred to the modality tools); a real description still makes them top tier.
    ctx = _ctx(scene_description="", file_type_assessment="document_scan", confidence=0.8)
    assert _is_top_tier_context(ctx) is True


def test_extracted_text_only_qualifies():
    ctx = _ctx(scene_description="", file_type_assessment="", extracted_text=["clause 1"])
    assert _is_top_tier_context(ctx) is True


def test_missing_confidence_treated_as_zero():
    ctx = _ctx(confidence=None)
    assert _is_top_tier_context(ctx) is False
