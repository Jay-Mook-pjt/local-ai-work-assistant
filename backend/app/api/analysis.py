from fastapi import APIRouter, Body, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, MeetingDep
from app.models import MeetingMinutes
from app.schemas.meeting import AnalyzeRequest, JobOut
from app.services import job_service, llm_service, settings_service

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/meetings/{id}/analyze", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def analyze(meeting: MeetingDep, db: DB, body: AnalyzeRequest = Body(default_factory=AnalyzeRequest)) -> JobOut:
    """Queue the STT + analysis pipeline (also used to retry or re-analyse with another model).

    If a transcript already exists for the current audio, the worker reuses it and only
    re-runs the LLM analysis — handy for comparing models.
    """
    if meeting.audio is None:
        raise HTTPException(409, "음성 파일을 먼저 업로드하세요.")
    minutes = db.scalar(select(MeetingMinutes).where(MeetingMinutes.meeting_id == meeting.id))
    if minutes is not None and minutes.edited and not body.overwrite_edited:
        raise HTTPException(409, "직접 수정한 회의록이 있습니다. 다시 분석하면 수정 내용이 새 결과로 바뀝니다. 계속하려면 덮어쓰기를 확인하세요.")
    model = body.llm_model or settings_service.llm_model(db)[0]
    if body.llm_model:
        try:
            if body.llm_model not in llm_service.installed_models():
                raise HTTPException(422, f"Ollama에 설치되지 않은 모델입니다: {body.llm_model}")
        except llm_service.LLMError as exc:
            raise HTTPException(503, str(exc)) from exc
    try:
        return JobOut.model_validate(job_service.enqueue(db, meeting, llm_model=model, retranscribe=body.retranscribe))
    except job_service.JobConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
