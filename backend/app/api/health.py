"""Health endpoint: backend, database, Ollama and STT readiness."""

import time

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.db.session import engine
from app.schemas.health import ComponentStatus, HealthResponse

router = APIRouter(tags=["health"])


def _check_db() -> ComponentStatus:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return ComponentStatus(ok=True)
    except Exception as exc:  # noqa: BLE001
        return ComponentStatus(ok=False, detail=str(exc))


async def _check_ollama() -> ComponentStatus:
    s = get_settings()
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=3) as client:
            version = (await client.get("/api/version")).raise_for_status().json().get("version")
            models = [m["name"] for m in (await client.get("/api/tags")).raise_for_status().json().get("models", [])]
    except Exception as exc:  # noqa: BLE001
        return ComponentStatus(ok=False, detail=f"Ollama 연결 실패: {exc}")
    latency = round((time.perf_counter() - start) * 1000, 1)
    if s.llm_model not in models:
        return ComponentStatus(ok=False, detail=f"모델 '{s.llm_model}' 미설치", version=version, latency_ms=latency, models=models)
    return ComponentStatus(ok=True, version=version, latency_ms=latency, models=models)


def _check_stt() -> ComponentStatus:
    try:
        import mlx.core as mx  # noqa: PLC0415
        import mlx_whisper  # noqa: F401, PLC0415

        return ComponentStatus(ok=True, detail=f"{get_settings().stt_model} on {mx.default_device()}")
    except Exception as exc:  # noqa: BLE001
        return ComponentStatus(ok=False, detail=f"MLX Whisper 사용 불가: {exc}")


@router.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    s = get_settings()
    db, ollama, stt = _check_db(), await _check_ollama(), _check_stt()
    return HealthResponse(
        status="ok" if all(c.ok for c in (db, ollama, stt)) else "degraded",
        env=s.app_env,
        llm_model=s.llm_model,
        components={"database": db, "ollama": ollama, "stt": stt},
    )
