from fastapi import APIRouter, HTTPException

from app.api.deps import DB
from app.config import get_settings
from app.schemas.meeting import SettingsOut, SettingsUpdate
from app.services import llm_service, settings_service

router = APIRouter(prefix="/api", tags=["settings"])


def _out(db: DB) -> SettingsOut:
    s = get_settings()
    model, source = settings_service.llm_model(db)
    try:
        available = llm_service.installed_models()
    except llm_service.LLMError:
        available = []
    return SettingsOut(
        llm_model=model,
        llm_model_source=source,  # type: ignore[arg-type]
        available_models=available,
        stt_model=s.stt_model,
        stt_language=s.stt_language,
        max_upload_mb=s.max_upload_mb,
        smtp_configured=s.smtp_configured,
    )


@router.get("/settings", response_model=SettingsOut)
def get_app_settings(db: DB) -> SettingsOut:
    return _out(db)


@router.put("/settings", response_model=SettingsOut)
def update_app_settings(body: SettingsUpdate, db: DB) -> SettingsOut:
    """Sets the default LLM for new analyses. Only models installed in Ollama are accepted."""
    try:
        installed = llm_service.installed_models()
    except llm_service.LLMError as exc:
        raise HTTPException(503, str(exc)) from exc
    if body.llm_model not in installed:
        raise HTTPException(422, f"Ollama에 설치되지 않은 모델입니다: {body.llm_model}")
    settings_service.set_value(db, settings_service.LLM_MODEL, body.llm_model)
    return _out(db)
