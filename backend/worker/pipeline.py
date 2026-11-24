"""Meeting processing pipeline run by the worker.

Stages: PREPROCESSING (ffmpeg → 16 kHz mono WAV) → TRANSCRIBING (MLX Whisper)
→ ANALYZING (Ollama, per chunk) → GENERATING (merge + validate) → COMPLETED.

PHASE 3 implements the pipeline framework and the PREPROCESSING stage.
TRANSCRIBING / ANALYZING / GENERATING are connected in PHASE 4; until then
the job stops with an explicit, retryable error instead of fake results.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Job, Meeting
from app.services import job_service, media, storage

log = logging.getLogger(__name__)


class PipelineError(Exception):
    """Expected failure with a user-facing message."""


@dataclass
class Context:
    db: Session
    job: Job
    meeting: Meeting

    def progress(self, status: str, progress: int, message: str) -> None:
        job_service.set_progress(self.db, self.job, status, progress, message)


def preprocess(ctx: Context) -> None:
    audio = ctx.meeting.audio
    if audio is None:
        raise PipelineError("음성 파일이 없습니다.")
    ctx.progress("PREPROCESSING", 8, "오디오를 16kHz 모노 WAV로 변환 중")
    src = storage.resolve(audio.stored_path)
    if not src.exists():
        raise PipelineError("원본 음성 파일을 찾을 수 없습니다. 다시 업로드하세요.")
    dst = storage.meeting_dir(storage.PROCESSED_DIR, ctx.meeting.id) / f"{audio.id}.wav"
    try:
        media.convert_to_wav16k(src, dst)
        info = media.probe(dst)
    except media.MediaError as exc:
        raise PipelineError(str(exc)) from exc
    audio.processed_path = storage.relative(dst)
    if info.duration_seconds:
        audio.duration_seconds = info.duration_seconds
    ctx.db.commit()
    ctx.progress("PREPROCESSING", 15, "오디오 변환 완료")


def transcribe(ctx: Context) -> None:
    raise PipelineError("음성 인식(MLX Whisper) 단계는 PHASE 4에서 연결됩니다. 오디오 변환까지는 정상 완료되었습니다.")


STAGES: list[tuple[str, Callable[[Context], None]]] = [
    ("PREPROCESSING", preprocess),
    ("TRANSCRIBING", transcribe),
]


def run(db: Session, job: Job) -> None:
    meeting = db.get(Meeting, job.meeting_id)
    if meeting is None:
        job_service.fail(db, job, "회의가 삭제되었습니다.")
        return
    ctx = Context(db=db, job=job, meeting=meeting)
    try:
        for name, stage in STAGES:
            log.info("Job %s: stage %s", job.id, name)
            stage(ctx)
        job_service.complete(db, job, "회의록 생성 완료")
    except PipelineError as exc:
        db.rollback()
        job_service.fail(db, job, str(exc))
    except Exception as exc:  # noqa: BLE001 - never let one job kill the worker
        log.exception("Job %s crashed", job.id)
        db.rollback()
        job_service.fail(db, job, f"예상하지 못한 오류: {type(exc).__name__}: {exc}")
