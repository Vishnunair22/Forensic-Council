"""WS-3 #11 regression: correlated detectors must fuse into one signal family
(no volume-bonus inflation), while genuinely distinct families count separately."""

from agents.arbiter_verdict import calculate_manipulation_probability


def _f(tool: str, conf: float, agent: str = "Agent1") -> dict:
    return {
        "agent_id": agent,
        "evidence_verdict": "POSITIVE",
        "confidence_raw": conf,
        "metadata": {"tool_name": tool, "confidence": conf},
    }


def test_correlated_compression_signals_fuse_to_one_family():
    # ELA + JPEG-ghost + frequency all respond to the SAME recompression artifact
    # (the "compression" family). They must count as ONE signal, not three, so a
    # re-encoded-but-authentic photo cannot climb on volume alone.
    findings = [
        _f("ela_full_image", 0.6),
        _f("jpeg_ghost_detect", 0.6),
        _f("frequency_domain_analysis", 0.6),
    ]
    prob, signals = calculate_manipulation_probability(findings)
    assert signals == 1, f"expected 1 fused family, got {signals}"
    # one family → single-signal downgrade caps it; never a manipulation verdict on volume
    assert prob <= 0.45


def test_distinct_families_count_separately():
    findings = [
        _f("ela_full_image", 0.8),            # compression
        _f("neural_splicing", 0.8),           # boundary
        _f("diffusion_artifact_detector", 0.8),  # generative
    ]
    _prob, signals = calculate_manipulation_probability(findings)
    assert signals == 3, f"expected 3 distinct families, got {signals}"


def test_no_volume_bonus_from_many_correlated_signals():
    # Many compression-family hits must not out-score the single STRONGEST member of
    # that family (volume bonus gone; fusion keeps the strongest, not the sum).
    strongest, _ = calculate_manipulation_probability([_f("frequency_domain_analysis", 0.7)])
    many, signals = calculate_manipulation_probability([
        _f("ela_full_image", 0.7),
        _f("jpeg_ghost_detect", 0.7),
        _f("frequency_domain_analysis", 0.7),
        _f("noise_fingerprint", 0.7),
        _f("neural_ela", 0.7),
    ])
    assert signals == 1, f"five compression signals must fuse to one family, got {signals}"
    assert many <= strongest + 0.001, f"volume inflated probability: strongest={strongest} many={many}"
