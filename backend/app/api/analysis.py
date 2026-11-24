from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, MeetingDep
from app.schemas.meeting import JobOut
from app.services import job_service

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/meetings/{id}/analyze", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def analyze(meeting: MeetingDep, db: DB) -> JobOut:
    """Queue (or re-queue after failure) the STT + analysis pipeline. The worker picks it up."""
    if meeting.audio is None:
        raise HTTPException(409, "음성 파일을 먼저 업로드하세요.")
    try:
        return JobOut.model_validate(job_service.enqueue(db, meeting))
    except job_service.JobConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
