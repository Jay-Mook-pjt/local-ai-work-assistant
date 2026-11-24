from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.api.deps import DB, MeetingDep
from app.config import get_settings
from app.schemas.meeting import MeetingOut
from app.services import audio_service

router = APIRouter(prefix="/api", tags=["audio"])


@router.post("/meetings/{id}/audio", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
def upload_audio(meeting: MeetingDep, db: DB, request: Request, file: UploadFile = File(...)) -> MeetingOut:
    # Cheap early reject before reading the body (multipart overhead allowed).
    limit = get_settings().max_upload_mb * 1024 * 1024
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > limit + 1024 * 1024:
        raise HTTPException(413, f"파일 크기가 {get_settings().max_upload_mb}MB를 초과합니다.")
    try:
        audio_service.save_upload(db, meeting, file.file, file.filename, file.content_type)
    except audio_service.UploadError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    finally:
        file.file.close()
    return MeetingOut.model_validate(meeting)
