"""Meeting processing pipeline run by the worker.

PREPROCESSING  ffmpeg → 16 kHz mono WAV                       5–15 %
TRANSCRIBING   MLX Whisper, windowed with overlap              15–55 %
               (skipped when a transcript of the same audio exists)
ANALYZING      Ollama, one call per transcript chunk           55–85 %
GENERATING     merge + grounding review + save minutes         85–100 %

STT and LLM never hold memory at the same time: the Whisper model is
unloaded before the first LLM call.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import meeting_agent
from app.config import get_settings
from app.models import Job, Meeting, Transcript
from app.services import job_service, llm_service, media, meeting_service, settings_service, storage, stt_service

log = logging.getLogger(__name__)


class PipelineError(Exception):
    """Expected failure with a user-facing message."""


@dataclass
class Context:
    db: Session
    job: Job
    meeting: Meeting
    segments: list[stt_service.Segment] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Injectable engines (tests replace these with fakes).
    transcribe_fn: Callable[..., dict] | None = None
    chat_fn: Callable[..., tuple] = llm_service.chat_json

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
        if not dst.exists():
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
    audio = ctx.meeting.audio
    assert audio is not None and audio.processed_path
    existing = ctx.db.scalar(select(Transcript).where(Transcript.meeting_id == ctx.meeting.id))
    if existing is not None and existing.audio_file_id == audio.id and existing.segments:
        ctx.segments = [stt_service.Segment(**s) for s in existing.segments]
        ctx.progress("TRANSCRIBING", 55, f"기존 전사문 재사용 ({len(ctx.segments)}개 구간)")
        return

    def on_progress(i: int, n: int) -> None:
        ctx.progress("TRANSCRIBING", 15 + int(40 * i / n), f"음성 인식 중 ({i + 1}/{n} 구간)" if n > 1 else "음성 인식 중")

    m = ctx.meeting
    try:
        segments = stt_service.transcribe(
            storage.resolve(audio.processed_path),
            initial_prompt=stt_service.build_initial_prompt(m.title, m.agenda, m.attendees),
            on_progress=on_progress,
            transcribe_fn=ctx.transcribe_fn,
        )
    except stt_service.STTError as exc:
        raise PipelineError(str(exc)) from exc
    finally:
        stt_service.unload_model()
    if not segments:
        raise PipelineError("음성에서 말소리를 인식하지 못했습니다. 녹음 상태를 확인하세요.")

    s = get_settings()
    data = [seg.__dict__ for seg in segments]
    if existing is None:
        existing = Transcript(meeting_id=m.id)
        ctx.db.add(existing)
    existing.audio_file_id = audio.id
    existing.language = s.stt_language
    existing.model = s.stt_model
    existing.segments = data
    existing.full_text = "\n".join(seg.text for seg in segments)
    ctx.db.commit()
    # Plain-text copy next to the audio for manual inspection/backup.
    out = storage.meeting_dir("transcripts", m.id) / "transcript.txt"
    out.write_text("\n".join(f"[{meeting_agent.review_agent.fmt_ts(x.start)}] {x.text}" for x in segments), encoding="utf-8")
    ctx.segments = segments
    ctx.progress("TRANSCRIBING", 55, f"음성 인식 완료 ({len(segments)}개 구간)")


def analyze(ctx: Context) -> None:
    model = ctx.job.llm_model or settings_service.llm_model(ctx.db)[0]

    def on_progress(stage: str, i: int, n: int) -> None:
        if stage == "ANALYZING":
            ctx.progress("ANALYZING", 55 + int(30 * i / n), f"AI 분석 중 · {model}" + (f" ({i + 1}/{n} 구간)" if n > 1 else ""))
        else:
            ctx.progress("GENERATING", 85 + 10 * i, f"회의록 통합 및 근거 검증 중 · {model}")

    try:
        result = meeting_agent.analyze(ctx.meeting, ctx.segments, model=model, on_progress=on_progress, chat=ctx.chat_fn)
    except llm_service.LLMError as exc:
        raise PipelineError(str(exc)) from exc
    meeting_service.save_minutes(ctx.db, ctx.meeting.id, result.minutes, llm_model=result.model, edited=False, review_notes=result.notes)
    ctx.notes = result.notes


STAGES: list[tuple[str, Callable[[Context], None]]] = [
    ("PREPROCESSING", preprocess),
    ("TRANSCRIBING", transcribe),
    ("ANALYZING", analyze),
]


def run(db: Session, job: Job, *, transcribe_fn: Callable[..., dict] | None = None, chat_fn: Callable[..., tuple] | None = None) -> None:
    meeting = db.get(Meeting, job.meeting_id)
    if meeting is None:
        job_service.fail(db, job, "회의가 삭제되었습니다.")
        return
    ctx = Context(db=db, job=job, meeting=meeting, transcribe_fn=transcribe_fn, chat_fn=chat_fn or llm_service.chat_json)
    try:
        for name, stage in STAGES:
            log.info("Job %s: stage %s", job.id, name)
            stage(ctx)
        msg = "회의록 생성 완료"
        if ctx.notes:
            msg += f" · 검토가 필요한 항목 {len(ctx.notes)}개"
        job_service.complete(db, job, msg)
    except PipelineError as exc:
        db.rollback()
        job_service.fail(db, job, str(exc))
    except Exception as exc:  # noqa: BLE001 - never let one job kill the worker
        log.exception("Job %s crashed", job.id)
        db.rollback()
        job_service.fail(db, job, f"예상하지 못한 오류: {type(exc).__name__}: {exc}")
