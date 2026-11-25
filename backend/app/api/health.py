"""Health endpoint: backend, database, Ollama and STT readiness."""

import time

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.db.session import SessionLocal, engine
from app.services import settings_service
from app.schemas.health import ComponentStatus, HealthResponse

router = APIRouter(tags=["health"])


def _check_db() -> ComponentStatus:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return ComponentStatus(ok=True)
    except Exception as exc:  # noqa: BLE001
        return ComponentStatus(ok=False, detail=str(exc))


def _effective_model() -> str:
    try:
        with SessionLocal() as db:
            return settings_service.llm_model(db)[0]
    except Exception:  # noqa: BLE001 - DB problems are reported by _check_db
        return get_settings().llm_model


async def _check_ollama(model: str) -> ComponentStatus:
    s = get_settings()
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=3) as client:
            version = (await client.get("/api/version")).raise_for_status().json().get("version")
            models = [
                m["name"] for m in (await client.get("/api/tags")).raise_for_status().json().get("models", [])
                if not m.get("remote_host") and not m["name"].lower().endswith(("-cloud", ":cloud"))
            ]
    except Exception as exc:  # noqa: BLE001
        return ComponentStatus(ok=False, detail=f"Ollama 연결 실패: {exc}")
    latency = round((time.perf_counter() - start) * 1000, 1)
    if model not in models:
        return ComponentStatus(ok=False, detail=f"모델 '{model}' 미설치", version=version, latency_ms=latency, models=models)
    return ComponentStatus(ok=True, version=version, latency_ms=latency, models=models)


def _check_diarization() -> ComponentStatus:
    s = get_settings()
    if not s.diarization_enabled:
        return ComponentStatus(ok=True, detail="사용 안 함 (DIARIZATION_ENABLED=false)")
    try:
        from app.services import diarization_service  # noqa: PLC0415

        if diarization_service.model_cached():
            return ComponentStatus(ok=True, detail=f"{s.diarization_model} (오프라인, 통계 전송 꺼짐)")
        return ComponentStatus(ok=False, detail="화자 분리 모델이 없습니다. 'python -m app.services.diarization_service download' 필요")
    except Exception as exc:  # noqa: BLE001
        return ComponentStatus(ok=False, detail=f"화자 분리 사용 불가: {exc}")


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
    model = _effective_model()
    db, ollama, stt, diar = _check_db(), await _check_ollama(model), _check_stt(), _check_diarization()
    return HealthResponse(
        status="ok" if all(c.ok for c in (db, ollama, stt, diar)) else "degraded",
        env=s.app_env,
        llm_model=model,
        components={"database": db, "ollama": ollama, "stt": stt, "diarization": diar},
    )
