"""Speech-to-text with MLX Whisper (Apple Silicon GPU).

Long recordings are transcribed in fixed windows (STT_CHUNK_SECONDS) that
overlap by STT_OVERLAP_SECONDS so words on a boundary are not cut. Segments
from the overlap are de-duplicated by keeping, for each boundary, the earlier
window's segments up to the overlap midpoint and the later window's after it.
"""

import logging
import re
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import get_settings

log = logging.getLogger(__name__)
SAMPLE_RATE = 16000

# Phrases Whisper commonly hallucinates on silence/music in Korean audio.
HALLUCINATIONS = (
    "시청해 주셔서 감사합니다",
    "시청해주셔서 감사합니다",
    "구독과 좋아요",
    "좋아요와 구독",
    "다음 영상에서 만나요",
    "MBC 뉴스",
    "자막 제공",
)


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None


class STTError(Exception):
    pass


def load_wav16k(path: Path) -> np.ndarray:
    """Reads the pipeline's 16 kHz mono PCM WAV into float32 [-1, 1] (no ffmpeg needed)."""
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise STTError("전처리된 오디오 형식이 올바르지 않습니다 (16kHz 모노 16bit 필요).")
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def plan_windows(duration: float, chunk: float, overlap: float) -> list[tuple[float, float]]:
    """[(start, end), ...] covering [0, duration] with the given overlap."""
    if duration <= chunk:
        return [(0.0, duration)]
    windows, start = [], 0.0
    step = chunk - overlap
    while start < duration:
        end = min(start + chunk, duration)
        windows.append((start, end))
        if end >= duration:
            break
        start += step
    return windows


def merge_windows(per_window: list[list[Segment]], windows: list[tuple[float, float]]) -> list[Segment]:
    """Drops duplicate segments produced in overlapping regions."""
    merged: list[Segment] = []
    for i, segs in enumerate(per_window):
        lo = (windows[i - 1][1] + windows[i][0]) / 2 if i > 0 else float("-inf")
        hi = (windows[i][1] + windows[i + 1][0]) / 2 if i + 1 < len(windows) else float("inf")
        for s in segs:
            mid = (s.start + s.end) / 2
            if lo <= mid < hi:
                merged.append(s)
    return merged


def _norm(text: str) -> str:
    return re.sub(r"[\s.,!?·…~\-]+", "", text)


def clean_segments(raw: list[dict], offset: float) -> list[Segment]:
    """Converts Whisper output to Segments, removing empty, hallucinated and looping text."""
    out: list[Segment] = []
    for r in raw:
        text = (r.get("text") or "").strip()
        if not text:
            continue
        if r.get("no_speech_prob", 0) > 0.6 and r.get("avg_logprob", 0) < -1.0:
            continue
        if any(h in text for h in HALLUCINATIONS):
            continue
        if r.get("compression_ratio", 0) > 2.6:  # repetitive loop
            continue
        if out and _norm(out[-1].text) == _norm(text):  # exact repeat of previous line
            continue
        out.append(Segment(start=round(offset + float(r["start"]), 2), end=round(offset + float(r["end"]), 2), text=text))
    return out


def build_initial_prompt(title: str, agenda: list[str], attendees: list[str]) -> str:
    """Vocabulary hint for Whisper (domain terms, names). Kept short: Whisper uses ≤224 tokens."""
    parts = [title, *agenda, *attendees]
    prompt = ", ".join(p for p in parts if p)
    return prompt[:300]


def transcribe(
    wav_path: Path,
    *,
    initial_prompt: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    transcribe_fn: Callable[..., dict] | None = None,
) -> list[Segment]:
    """Transcribes a 16 kHz mono WAV. `transcribe_fn` is injectable for tests."""
    s = get_settings()
    audio = load_wav16k(wav_path)
    duration = len(audio) / SAMPLE_RATE
    windows = plan_windows(duration, s.stt_chunk_seconds, s.stt_overlap_seconds)
    fn = transcribe_fn or _mlx_transcribe
    per_window: list[list[Segment]] = []
    t0 = time.perf_counter()
    for i, (start, end) in enumerate(windows):
        if on_progress:
            on_progress(i, len(windows))
        chunk = audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)]
        result = fn(
            chunk,
            path_or_hf_repo=s.stt_model,
            language=s.stt_language,
            initial_prompt=initial_prompt,
            # Conditioning on previous text makes Whisper loop on long Korean audio.
            condition_on_previous_text=False,
            verbose=None,
        )
        per_window.append(clean_segments(result.get("segments", []), offset=start))
    segments = merge_windows(per_window, windows)
    elapsed = time.perf_counter() - t0
    log.info("STT %s: %.0fs audio, %d window(s), %d segments in %.1fs (x%.1f realtime)",
             wav_path.name, duration, len(windows), len(segments), elapsed, duration / elapsed if elapsed else 0)
    return segments


def _mlx_transcribe(audio: np.ndarray, **kwargs) -> dict:
    import mlx_whisper  # noqa: PLC0415 - heavy import, only in the worker

    return mlx_whisper.transcribe(audio, **kwargs)


def unload_model() -> None:
    """Frees the Whisper model so the LLM has the unified memory to itself."""
    try:
        import mlx.core as mx  # noqa: PLC0415
        from mlx_whisper.transcribe import ModelHolder  # noqa: PLC0415

        ModelHolder.model = None
        ModelHolder.model_path = None
        mx.clear_cache()
    except Exception:  # noqa: BLE001
        log.debug("Whisper model unload skipped", exc_info=True)
