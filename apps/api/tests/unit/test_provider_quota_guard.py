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
