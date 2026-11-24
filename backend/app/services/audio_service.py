"""Validated audio upload: extension + MIME + file signature + size limit + ffprobe."""

import logging
import unicodedata
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AudioFile, Meeting, new_id
from app.services import job_service, media, storage

log = logging.getLogger(__name__)
CHUNK = 1024 * 1024


class UploadError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def safe_display_name(raw: str | None) -> str:
    """Original filename for display only: basename, NFC, control chars removed."""
    name = unicodedata.normalize("NFC", raw or "")
    name = PureWindowsPath(PurePosixPath(name).name).name  # strip any directory part (/ or \)
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:255]


def save_upload(db: Session, meeting: Meeting, stream: BinaryIO, filename: str | None, content_type: str | None) -> AudioFile:
    s = get_settings()
    if job_service.active_job(db, meeting.id):
        raise UploadError("처리 중인 회의에는 음성 파일을 다시 올릴 수 없습니다.", 409)

    name = safe_display_name(filename)
    ext = Path(name).suffix.lower().lstrip(".")
    if not name or ext not in s.allowed_extension_set or ext not in media.ALLOWED_MIME:
        raise UploadError(f"지원하지 않는 형식입니다. ({', '.join(sorted(s.allowed_extension_set)).upper()}만 가능)", 415)
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in media.ALLOWED_MIME[ext] and mime not in media.GENERIC_MIME:
        raise UploadError(f"파일 형식({mime})이 확장자(.{ext})와 맞지 않습니다.", 415)

    max_bytes = s.max_upload_mb * 1024 * 1024
    audio_id = new_id()
    target_dir = storage.meeting_dir(storage.ORIGINAL_DIR, meeting.id)
    tmp = target_dir / f"{audio_id}.uploading"
    size = 0
    head = b""
    try:
        with tmp.open("wb") as out:
            while chunk := stream.read(CHUNK):
                if not head:
                    head = chunk[:64]
                size += len(chunk)
                if size > max_bytes:
                    raise UploadError(f"파일 크기가 {s.max_upload_mb}MB를 초과합니다.", 413)
                out.write(chunk)
        if size == 0:
            raise UploadError("빈 파일입니다.")
        if not media.signature_matches(ext, head):
            raise UploadError(f"파일 내용이 .{ext} 형식이 아닙니다.", 415)
        info = media.probe(tmp)
        if not info.has_audio:
            raise UploadError("오디오 트랙이 없는 파일입니다.", 415)
        final = target_dir / f"{audio_id}.{ext}"
        tmp.replace(final)
    except media.MediaError as exc:
        tmp.unlink(missing_ok=True)
        raise UploadError(str(exc), 415) from exc
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    # Replace a previous upload (and its derived files) for this meeting.
    old = meeting.audio
    if old is not None:
        for rel in (old.stored_path, old.processed_path):
            if rel:
                storage.resolve(rel).unlink(missing_ok=True)
        db.delete(old)
        db.flush()

    audio = AudioFile(
        id=audio_id,
        meeting_id=meeting.id,
        original_filename=name,
        stored_path=storage.relative(final),
        size_bytes=size,
        mime_type=mime if mime not in media.GENERIC_MIME else f"audio/{ext}",
        format_name=info.format_name,
        duration_seconds=info.duration_seconds,
    )
    db.add(audio)
    meeting.status = "UPLOADED"
    db.commit()
    db.refresh(meeting)
    log.info("Stored audio for meeting %s: %s (%d bytes, %.1fs)", meeting.id, name, size, info.duration_seconds or -1)
    return audio
