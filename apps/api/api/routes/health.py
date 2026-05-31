"""Health, liveness, and system-probe routes.

Extracted from api/main.py to keep the app-assembly file small.
"""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.middleware._common import settings_from_app

router = APIRouter(tags=["health"])


@router.get("/live")
@router.get("/api/v1/live")
async def liveness_check():
    """Lightweight liveness probe — returns 200 immediately."""
    return JSONResponse(content={"status": "alive"}, status_code=200)


@router.get("/health")
@router.get("/api/v1/health")
async def health_check(request: Request):
    """Deep health check — verifies all infrastructure dependencies."""
    settings = settings_from_app(request)
    checks: dict = {}
    overall_healthy = True

    migrations_ok = getattr(request.app.state, "migrations_ok", True)
    checks["migrations"] = "ok" if migrations_ok else "failed"
    if not migrations_ok:
        overall_healthy = False

    try:
        from core.persistence.postgres_client import (
            get_postgres_client as get_health_postgres_client,
        )
        pg = await get_health_postgres_client()
        if hasattr(pg, "fetch_val"):
            await pg.fetch_val("SELECT 1")
        elif hasattr(pg, "ping"):
            await pg.ping()
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = "error: connection failed"
        if settings.debug:
            checks["postgres_debug"] = f"{type(e).__name__}: {str(e)[:100]}"
        overall_healthy = False

    try:
        from core.persistence.redis_client import get_redis_client as get_health_redis_client
        redis = await get_health_redis_client()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = "error: connection failed"
        if settings.debug:
            checks["redis_debug"] = f"{type(e).__name__}: {str(e)[:100]}"
        overall_healthy = False

    try:
        from core.pdf_report_exporter import probe_pdf_libs
        checks["pdf_export"] = probe_pdf_libs()
    except Exception:
        checks["pdf_export"] = {"weasyprint": False, "fpdf2": False}

    try:
        from core.persistence.qdrant_client import get_qdrant_client as get_health_qdrant_client
        qdrant = await get_health_qdrant_client()
        if hasattr(qdrant, "health_check"):
            await qdrant.health_check()
        elif hasattr(qdrant, "ping"):
            await qdrant.ping()
        checks["qdrant"] = "ok"
    except Exception as e:
        checks["qdrant"] = "error: connection failed"
        if settings.debug:
            checks["qdrant_debug"] = f"{type(e).__name__}: {str(e)[:100]}"
        overall_healthy = False

    return JSONResponse(
        status_code=200 if overall_healthy or settings.app_env == "testing" else 503,
        content={"status": "ok" if overall_healthy else "degraded", "checks": checks},
    )


@router.get("/api/v1/health/ml-tools")
async def ml_tools_health():
    """ML tools warm-up status endpoint."""
    from core.config import get_settings
    from core.ml_subprocess import get_warmup_status, health_check_ml_tools

    settings = get_settings()
    warmup_status = get_warmup_status()
    script_status = await health_check_ml_tools()

    tools_present = sum(1 for v in script_status.values() if v != "script_not_found")
    tools_total = len(script_status)
    tools_warmed = sum(1 for v in warmup_status.values() if v)

    return {
        "status": "available" if tools_present == tools_total else "missing_scripts",
        "tools_present": tools_present,
        "tools_total": tools_total,
        "warmup_status": "managed_by_worker",
        "tools_warmed_in_process": tools_warmed,
        "presence_percentage": round(
            (tools_present / tools_total * 100) if tools_total > 0 else 0, 1
        ),
        "details": script_status,
        "warmup_details": warmup_status,
        "cache_dirs": {
            "torch": str(settings.torch_home),
            "huggingface": str(settings.hf_home),
            "ultralytics": str(settings.yolo_model_dir),
            "easyocr": str(getattr(settings, "easyocr_model_dir", "/app/cache/easyocr")),
        },
    }


@router.get("/api/v1/health/tools")
async def system_tools_health():
    """Check availability of external system dependencies."""
    tools = {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "exiftool": shutil.which("exiftool") is not None,
        "tesseract": shutil.which("tesseract") is not None,
    }

    missing = [tool for tool, present in tools.items() if not present]
    status = "healthy" if not missing else "degraded"

    return {
        "status": status,
        "tools": tools,
        "missing": missing,
        "message": "All required system tools are present"
        if not missing
        else f"Missing system tools: {', '.join(missing)}",
    }


@router.get("/api/v1/health/providers")
async def providers_health(request: Request):
    """Health and rate-limiting status for the LLM provider cascade."""
    settings = settings_from_app(request)
    from core.llm_client import is_placeholder_secret
    from core.provider_quota_guard import ProviderQuotaGuard

    v_chain_str = getattr(settings, "vision_provider_chain", "gemini,groq_vision,openrouter,local_ensemble")
    v_chain = [p.strip().lower() for p in v_chain_str.split(",") if p.strip()]

    t_chain_str = getattr(settings, "text_provider_chain", "gemini,groq,openrouter,cerebras,local")
    t_chain = [p.strip().lower() for p in t_chain_str.split(",") if p.strip()]

    providers_status = {}

    gemini_key = settings.gemini_api_key
    gemini_configured = bool(gemini_key and not is_placeholder_secret(gemini_key))
    gemini_rpm, gemini_rpd = ProviderQuotaGuard.get_current_counts("gemini", "gemini-2.5-flash")
    providers_status["gemini"] = {
        "enabled": "gemini" in v_chain or "gemini" in t_chain,
        "configured": gemini_configured,
        "quota": {
            "current_rpm": gemini_rpm,
            "rpm_limit": settings.gemini_rpm_limit,
            "current_rpd": gemini_rpd,
            "rpd_limit": settings.gemini_rpd_limit,
        },
    }

    groq_key = settings.groq_vision_api_key
    if not groq_key or groq_key.strip() == "":
        if getattr(settings, "llm_provider", "").lower() == "groq":
            groq_key = settings.llm_api_key
    groq_configured = bool(groq_key and not is_placeholder_secret(groq_key))
    groq_model = settings.groq_vision_model or "llama-3.2-11b-vision-preview"
    groq_rpm, groq_rpd = ProviderQuotaGuard.get_current_counts("groq_vision", groq_model)
    providers_status["groq_vision"] = {
        "enabled": "groq_vision" in v_chain,
        "configured": groq_configured,
        "model": groq_model,
        "quota": {
            "current_rpm": groq_rpm,
            "rpm_limit": settings.groq_vision_rpm_limit,
            "current_rpd": groq_rpd,
            "rpd_limit": settings.groq_vision_rpd_limit,
        },
    }

    or_enabled = getattr(settings, "openrouter_enabled", False)
    or_key = settings.openrouter_api_key
    or_configured = bool(or_key and not is_placeholder_secret(or_key))
    or_models = [m.strip() for m in settings.openrouter_vision_models.split(",") if m.strip()]
    or_rpm, or_rpd = 0, 0
    if or_models:
        or_rpm, or_rpd = ProviderQuotaGuard.get_current_counts("openrouter", or_models[0])
    providers_status["openrouter"] = {
        "enabled": "openrouter" in v_chain or "openrouter" in t_chain,
        "configured": or_configured and or_enabled,
        "models": or_models,
        "quota": {
            "current_rpm": or_rpm,
            "rpm_limit": settings.openrouter_rpm_limit,
            "current_rpd": or_rpd,
            "rpd_limit": settings.openrouter_rpd_limit,
        },
    }

    providers_status["local_ensemble"] = {
        "enabled": "local_ensemble" in v_chain,
        "configured": True,
        "quota": None,
    }

    return {
        "status": "healthy",
        "vision_provider_chain": v_chain,
        "text_provider_chain": t_chain,
        "providers": providers_status,
    }
