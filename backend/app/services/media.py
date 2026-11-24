"""Audio inspection/conversion with ffprobe/ffmpeg, and file-signature checks."""

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)

# Extension -> accepted client-reported MIME types.
ALLOWED_MIME: dict[str, set[str]] = {
    "mp3": {"audio/mpeg", "audio/mp3"},
    "wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
    "m4a": {"audio/mp4", "audio/x-m4a", "audio/m4a", "audio/aac"},
    "mp4": {"video/mp4", "audio/mp4"},
}
# Browsers/curl sometimes send these for any file; the content check still applies.
GENERIC_MIME = {"", "application/octet-stream"}


class MediaError(Exception):
    """Raised when a file is not usable audio. Message is shown to the user."""


def find_binary(name: str) -> str:
    """Resolve ffmpeg/ffprobe even under launchd's minimal PATH."""
    found = shutil.which(name) or shutil.which(Path(name).name, path="/opt/homebrew/bin:/usr/local/bin")
    if not found:
        raise MediaError(f"{name}을(를) 찾을 수 없습니다. 'brew install ffmpeg'로 설치하세요.")
    return found


def sniff_format(head: bytes) -> str | None:
    """Detect the container from the first bytes. Returns an extension or None."""
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "mp4"  # MP4/M4A share the ISO-BMFF container
    if head[:3] == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    return None


def signature_matches(ext: str, head: bytes) -> bool:
    sniffed = sniff_format(head)
    return sniffed == ext or (ext in ("m4a", "mp4") and sniffed == "mp4")


@dataclass(frozen=True)
class ProbeResult:
    duration_seconds: float | None
    format_name: str
    has_audio: bool


def probe(path: Path, timeout: float = 60) -> ProbeResult:
    cmd = [find_binary(get_settings().ffprobe_bin), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True).stdout
    except subprocess.CalledProcessError as exc:
        raise MediaError(f"오디오 파일을 읽을 수 없습니다: {exc.stderr.strip()[:300] or '형식 오류'}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError("오디오 파일 분석 시간이 초과되었습니다.") from exc
    data = json.loads(out or "{}")
    fmt = data.get("format", {})
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    try:
        duration = float(fmt["duration"])
    except (KeyError, TypeError, ValueError):
        duration = None
    return ProbeResult(duration_seconds=duration, format_name=fmt.get("format_name", ""), has_audio=has_audio)


def convert_to_wav16k(src: Path, dst: Path, timeout: float = 3600) -> None:
    """Decode any supported input (incl. MP4 video) to 16 kHz mono PCM WAV for STT."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".partial.wav")
    cmd = [find_binary(get_settings().ffmpeg_bin), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
    except subprocess.CalledProcessError as exc:
        tmp.unlink(missing_ok=True)
        raise MediaError(f"ffmpeg 변환 실패: {exc.stderr.strip()[:500]}") from exc
    except subprocess.TimeoutExpired as exc:
        tmp.unlink(missing_ok=True)
        raise MediaError("ffmpeg 변환 시간이 초과되었습니다.") from exc
    tmp.replace(dst)
