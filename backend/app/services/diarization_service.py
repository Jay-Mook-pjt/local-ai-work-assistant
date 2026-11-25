"""Speaker diarization with pyannote.audio — fully local after a one-time download.

Privacy: pyannote.audio 4.x ships usage telemetry (model name, audio duration,
speaker count → otel.pyannote.ai) that is ON by default. It is switched off here
*before* pyannote is imported, and the Hugging Face hub runs in offline mode
when processing meetings, so no audio metadata leaves this Mac.

One-time setup (needs the user's HF token in the macOS Keychain):
    .venv/bin/python -m app.services.diarization_service download
"""

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

# Must be set before `import pyannote.audio` (read at import time). The API and the
# worker also set these (plus HF offline mode) at process start, see app/offline.py.
os.environ["PYANNOTE_METRICS_ENABLED"] = "false"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

log = logging.getLogger(__name__)
SAMPLE_RATE = 16000


class DiarizationError(Exception):
    pass


@dataclass
class Turn:
    start: float
    end: float
    speaker: str  # "SPEAKER_00" …


def _hf_token() -> str:
    s = get_settings()
    try:
        r = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", s.hf_keychain_service, "-a", s.hf_keychain_account, "-w"],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise DiarizationError("macOS 키체인에서 Hugging Face 토큰을 찾지 못했습니다. README의 화자 분리 설정을 참고하세요.") from exc
    return r.stdout.strip()


def model_cached() -> bool:
    """True if the pipeline can be loaded offline (project models/ folder or HF cache)."""
    from app.services import model_store  # noqa: PLC0415

    if model_store.local_path(get_settings().diarization_model):
        return all(c.ok for c in model_store.verify() if c.key == "diarization")
    from huggingface_hub import try_to_load_from_cache  # noqa: PLC0415

    return isinstance(try_to_load_from_cache(get_settings().diarization_model, "config.yaml"), str)


def download() -> Path:
    """One-time model download (online, uses the HF token). Returns the cache path."""
    if os.environ.get("HF_HUB_OFFLINE") == "1":
        raise DiarizationError("오프라인 모드에서는 내려받을 수 없습니다. 'python -m app.services.diarization_service download'로 실행하세요.")
    from huggingface_hub import snapshot_download  # noqa: PLC0415

    path = snapshot_download(get_settings().diarization_model, token=_hf_token())
    log.info("Downloaded %s", get_settings().diarization_model)
    return Path(path)


_pipeline = None


def _device():
    import torch  # noqa: PLC0415

    want = get_settings().diarization_device
    if want == "cpu" or (want == "auto" and not torch.backends.mps.is_available()):
        return torch.device("cpu")
    return torch.device("mps")


def load_pipeline():
    """Loads the cached pipeline without network access."""
    global _pipeline
    if _pipeline is None:
        try:
            from pyannote.audio import Pipeline  # noqa: PLC0415

            from app.services import model_store  # noqa: PLC0415

            _pipeline = Pipeline.from_pretrained(model_store.resolve(get_settings().diarization_model))
        except Exception as exc:  # noqa: BLE001
            raise DiarizationError(
                f"화자 분리 모델을 불러오지 못했습니다. 최초 1회 'python -m app.services.diarization_service download'가 필요합니다. ({type(exc).__name__})"
            ) from exc
        if _pipeline is None:
            raise DiarizationError("화자 분리 모델을 불러오지 못했습니다 (모델 약관 동의 여부를 확인하세요).")
        _pipeline.to(_device())
    return _pipeline


def unload() -> None:
    global _pipeline
    _pipeline = None
    import gc  # noqa: PLC0415

    gc.collect()
    try:
        import torch  # noqa: PLC0415

        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def diarize(wav_path: Path, num_speakers: int | None = None, min_speakers: int | None = None, max_speakers: int | None = None) -> list[Turn]:
    """Speaker turns for a 16 kHz mono WAV (the pipeline's preprocessed file)."""
    import torch  # noqa: PLC0415

    from app.services.stt_service import load_wav16k  # noqa: PLC0415

    audio = torch.from_numpy(load_wav16k(wav_path)).unsqueeze(0)
    pipeline = load_pipeline()
    t0 = time.perf_counter()
    kwargs = {k: v for k, v in {"num_speakers": num_speakers, "min_speakers": min_speakers, "max_speakers": max_speakers}.items() if v}
    out = pipeline({"waveform": audio, "sample_rate": SAMPLE_RATE}, **kwargs)
    # pyannote 4: output object with an "exclusive" variant (one speaker at a time),
    # which aligns better with STT segments; pyannote 3: an Annotation.
    # (Explicit None checks: an empty Annotation is falsy, e.g. a recording with no speech.)
    ann = getattr(out, "exclusive_speaker_diarization", None)
    if ann is None:
        ann = getattr(out, "speaker_diarization", None)
    if ann is None:
        ann = out
    turns = [Turn(round(seg.start, 2), round(seg.end, 2), str(label)) for seg, _, label in ann.itertracks(yield_label=True)]
    log.info("Diarization %s: %d turns, %d speakers in %.1fs", wav_path.name, len(turns), len({t.speaker for t in turns}), time.perf_counter() - t0)
    return turns


def assign_speakers(segments: list, turns: list[Turn], max_gap: float = 1.0) -> list[str | None]:
    """Speaker label for each STT segment: the turn with the largest time overlap,
    else the nearest turn within `max_gap` seconds, else None."""
    return [_speaker_at(seg.start, seg.end, turns, max_gap) for seg in segments]


def _speaker_at(start: float, end: float, turns: list[Turn], max_gap: float = 1.0) -> str | None:
    best, best_overlap = None, 0.0
    for t in turns:
        ov = min(end, t.end) - max(start, t.start)
        if ov > best_overlap:
            best, best_overlap = t.speaker, ov
    if best is None and turns:
        mid = (start + end) / 2
        near = min(turns, key=lambda t: min(abs(mid - t.start), abs(mid - t.end)))
        if min(abs(mid - near.start), abs(mid - near.end)) <= max_gap:
            best = near.speaker
    return best


def display_labels(raw: list[str | None]) -> list[str | None]:
    """SPEAKER_03 → '화자 1' numbered by first appearance."""
    order: dict[str, str] = {}
    labels: list[str | None] = []
    for r in raw:
        if r is None:
            labels.append(None)
            continue
        if r not in order:
            order[r] = f"화자 {len(order) + 1}"
        labels.append(order[r])
    return labels


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "download":
        print(download())
    else:
        print(__doc__)
