"""Meeting analysis: transcript → (chunked) LLM extraction → merge → grounding review.

Short meetings (one chunk) use a single LLM call. Long meetings are split on
segment boundaries into ~LLM_CHUNK_CHARS pieces (with two lines of overlap
for context), analysed one by one, then merged by a second call that only
sees the structured extracts — the full transcript is never sent at once.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.agents import review_agent, task_agent
from app.agents.llm_schemas import ChunkAnalysis, FinalMinutes
from app.config import get_settings
from app.models import Meeting
from app.schemas.meeting import MinutesUpdate
from app.services import llm_service, prompt_service
from app.services.stt_service import Segment

log = logging.getLogger(__name__)
CONTEXT_LINES = 2


@dataclass
class AnalysisResult:
    minutes: MinutesUpdate
    notes: list[str]
    model: str
    llm_calls: int
    llm_seconds: float


def format_line(seg: Segment) -> str:
    who = f"{seg.speaker}: " if seg.speaker else ""
    return f"[{review_agent.fmt_ts(seg.start)}] {who}{seg.text}"


def apply_speaker_names(segments: list[Segment], names: dict[str, str] | None) -> list[Segment]:
    """'화자 2' → '박정우 책임' where the user named the speaker."""
    if not names:
        return segments
    return [Segment(s.start, s.end, s.text, names.get(s.speaker or "", s.speaker)) for s in segments]


def chunk_transcript(segments: list[Segment], max_chars: int) -> list[str]:
    """Splits on segment boundaries; each chunk after the first starts with context lines."""
    chunks: list[list[str]] = []
    current: list[str] = []
    size = 0
    for i, seg in enumerate(segments):
        line = format_line(seg)
        if current and size + len(line) + 1 > max_chars:
            chunks.append(current)
            ctx = [f"(이전 구간에서 이어짐) {format_line(s)}" for s in segments[max(0, i - CONTEXT_LINES) : i]]
            current, size = list(ctx), sum(len(c) + 1 for c in ctx)
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append(current)
    return ["\n".join(c) for c in chunks]


def _meeting_fields(m: Meeting) -> dict[str, str]:
    return {
        "title": m.title,
        "meeting_date": m.meeting_date.isoformat(),
        "attendees": ", ".join(m.attendees) or "미입력",
        "purpose": m.purpose or "미입력",
        "agenda": "\n".join(f"  {i + 1}. {a}" for i, a in enumerate(m.agenda)) or "  (미입력)",
        "instructions": m.instructions or "(없음)",
    }


def analyze(
    meeting: Meeting,
    segments: list[Segment],
    *,
    model: str | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    chat: Callable[..., tuple] = llm_service.chat_json,
    glossary: str = "",
) -> AnalysisResult:
    if not segments:
        raise llm_service.LLMError("전사문이 비어 있어 회의록을 만들 수 없습니다. 음성에 말소리가 있는지 확인하세요.")
    s = get_settings()
    model = model or s.llm_model
    segments = apply_speaker_names(segments, meeting.speaker_names)
    system = prompt_service.system_prompt(glossary)
    fields = _meeting_fields(meeting)
    chunks = chunk_transcript(segments, s.llm_chunk_chars)
    calls, seconds = 0, 0.0

    if len(chunks) == 1:
        if on_progress:
            on_progress("ANALYZING", 0, 1)
        final, st = chat(system=system, user=prompt_service.render("single", **fields, transcript=chunks[0]), schema=FinalMinutes, model=model, purpose="single")
        calls, seconds = 1, st.seconds
    else:
        extracts: list[ChunkAnalysis] = []
        for i, text in enumerate(chunks):
            if on_progress:
                on_progress("ANALYZING", i, len(chunks))
            part = "처음" if i == 0 else ("마지막" if i == len(chunks) - 1 else "중간")
            res, st = chat(
                system=system,
                user=prompt_service.render("chunk", **fields, part=part, part_index=i + 1, part_total=len(chunks), transcript=text),
                schema=ChunkAnalysis,
                model=model,
                purpose=f"chunk {i + 1}/{len(chunks)}",
            )
            extracts.append(res)
            calls, seconds = calls + 1, seconds + st.seconds
        if on_progress:
            on_progress("GENERATING", 0, 1)
        payload = json.dumps([{"구간": i + 1, **e.model_dump()} for i, e in enumerate(extracts)], ensure_ascii=False, indent=1)
        final, st = chat(system=system, user=prompt_service.render("merge", **fields, chunks=payload), schema=FinalMinutes, model=model, purpose="merge")
        calls, seconds = calls + 1, seconds + st.seconds

    if on_progress:
        on_progress("GENERATING", 1, 1)
    duration = meeting.audio.duration_seconds if meeting.audio else None
    info = " ".join([meeting.title, meeting.purpose, *meeting.agenda, meeting.instructions, meeting.meeting_date.isoformat()])
    reviewed = review_agent.review(final, segments, meeting.agenda, duration, meeting.attendees, meeting_info=info)
    reviewed.notes += task_agent.correct_names(reviewed.minutes, meeting.attendees)
    reviewed.minutes.action_items = task_agent.normalize(reviewed.minutes.action_items, meeting.attendees)
    log.info("Analysis of meeting %s: %d chunk(s), %d LLM call(s), %.1fs, %d review note(s)", meeting.id, len(chunks), calls, seconds, len(reviewed.notes))
    return AnalysisResult(minutes=reviewed.minutes, notes=reviewed.notes, model=model, llm_calls=calls, llm_seconds=round(seconds, 1))
