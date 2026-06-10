import asyncio

import pytest

from core.provider_quota_guard import ProviderQuotaGuard


@pytest.fixture(autouse=True)
def _clear_quota_guard():
    ProviderQuotaGuard.clear_all()
    ProviderQuotaGuard._configs.clear()
    yield
    ProviderQuotaGuard.clear_all()
    ProviderQuotaGuard._configs.clear()


@pytest.mark.asyncio
async def test_check_and_record_is_atomic_for_concurrent_rpm_limit():
    ProviderQuotaGuard.configure("groq", rpm_limit=2, rpd_limit=100)

    results = await asyncio.gather(
        *[
            ProviderQuotaGuard.check_and_record("groq", "llama-3.3-70b-versatile")
            for _ in range(5)
        ]
    )

    allowed = [allowed for allowed, _ in results]
    assert allowed.count(True) == 2
    assert allowed.count(False) == 3


@pytest.mark.asyncio
async def test_check_and_record_blocks_projected_tpm_overrun():
    ProviderQuotaGuard.configure("groq", rpm_limit=10, rpd_limit=100, tpm_limit=1000)

    first_allowed, first_result = await ProviderQuotaGuard.check_and_record(
        "groq",
        "llama-3.3-70b-versatile",
        estimated_tokens=700,
    )
    second_allowed, second_result = await ProviderQuotaGuard.check_and_record(
        "groq",
        "llama-3.3-70b-versatile",
        estimated_tokens=400,
    )

    assert first_allowed is True
    assert first_result.window_type == "rpm"
    assert second_allowed is False
    assert second_result.window_type == "tpm"


@pytest.mark.asyncio
async def test_critical_priority_bypasses_tpm_soft_block():
    # A medium call exhausts the TPM budget; a following critical call (e.g. the
    # final-report refiner) must still be allowed through the soft TPM pre-block
    # so it is not silently dropped to the deterministic narrative.
    ProviderQuotaGuard.configure("groq", rpm_limit=10, rpd_limit=100, tpm_limit=1000)

    medium_allowed, _ = await ProviderQuotaGuard.check_and_record(
        "groq", "llama-3.3-70b-versatile", estimated_tokens=900, priority="medium"
    )
    blocked_allowed, blocked_result = await ProviderQuotaGuard.check_and_record(
        "groq", "llama-3.3-70b-versatile", estimated_tokens=400, priority="medium"
    )
    critical_allowed, _ = await ProviderQuotaGuard.check_and_record(
        "groq", "llama-3.3-70b-versatile", estimated_tokens=400, priority="critical"
    )

    assert medium_allowed is True
    assert blocked_allowed is False
    assert blocked_result.window_type == "tpm"
    # Critical bypasses the TPM soft-block even though the budget is exhausted.
    assert critical_allowed is True


@pytest.mark.asyncio
async def test_critical_priority_still_enforces_rpm():
    # Critical bypasses only the soft TPM check — the hard RPM request-count
    # limit remains enforced so a stuck critical caller cannot hammer the API.
    ProviderQuotaGuard.configure("groq", rpm_limit=2, rpd_limit=100, tpm_limit=100000)

    results = [
        await ProviderQuotaGuard.check_and_record(
            "groq", "llama-3.3-70b-versatile", estimated_tokens=10, priority="critical"
        )
        for _ in range(4)
    ]
    allowed = [a for a, _ in results]
    assert allowed.count(True) == 2
    assert allowed.count(False) == 2
    assert results[-1][1].window_type == "rpm"
