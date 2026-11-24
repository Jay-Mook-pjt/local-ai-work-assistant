import subprocess

import pytest

from app.config import get_settings
from app.services import stt_service
from app.services.media import find_binary
from app.services.stt_service import Segment, clean_segments, merge_windows, plan_windows
from tests.fakes import FakeWhisper


def test_plan_windows_short_audio_is_one_window():
    assert plan_windows(300, 600, 10) == [(0.0, 300)]


def test_plan_windows_overlap():
    w = plan_windows(1500, 600, 10)
    assert w == [(0.0, 600), (590.0, 1190.0), (1180.0, 1500)]


def test_merge_windows_removes_overlap_duplicates():
    windows = [(0.0, 600), (590.0, 1190.0)]
    a = [Segment(580, 588, "앞 창의 마지막 문장"), Segment(592, 599, "겹치는 문장")]
    b = [Segment(592.3, 599.2, "겹치는 문장"), Segment(610, 620, "뒤 창의 문장")]
    merged = merge_windows([a, b], windows)
    assert [s.text for s in merged] == ["앞 창의 마지막 문장", "겹치는 문장", "뒤 창의 문장"]


def test_clean_segments_filters_hallucinations_and_repeats():
    raw = [
        {"start": 0, "end": 2, "text": " 안녕하세요 "},
        {"start": 2, "end": 4, "text": "안녕하세요."},  # repeat
        {"start": 4, "end": 6, "text": "시청해 주셔서 감사합니다."},  # hallucination
        {"start": 6, "end": 8, "text": "", "no_speech_prob": 0.1},
        {"start": 8, "end": 9, "text": "음음음", "no_speech_prob": 0.9, "avg_logprob": -1.5},
        {"start": 9, "end": 10, "text": "네 네 네 네 네 네", "compression_ratio": 3.0},
        {"start": 10, "end": 12, "text": "다음 안건입니다"},
    ]
    out = clean_segments(raw, offset=100)
    assert [(s.start, s.text) for s in out] == [(100, "안녕하세요"), (110, "다음 안건입니다")]


def test_initial_prompt_contains_domain_terms():
    p = stt_service.build_initial_prompt("방카슈랑스 회의", ["CheckMATE 오류"], ["이지은 대리"])
    assert "CheckMATE" in p and "이지은" in p and len(p) <= 300


@pytest.fixture
def long_wav(tmp_path):
    """35 minutes of silence as 16 kHz mono WAV (small on disk for a test)."""
    p = tmp_path / "long.wav"
    subprocess.run(
        [find_binary("ffmpeg"), "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "2100", "-c:a", "pcm_s16le", str(p)],
        check=True,
    )
    return p


def test_transcribe_windows_offsets_and_progress(long_wav, monkeypatch):
    monkeypatch.setattr(get_settings(), "stt_chunk_seconds", 600)
    monkeypatch.setattr(get_settings(), "stt_overlap_seconds", 10)
    fake = FakeWhisper()
    windows = plan_windows(2100, 600, 10)

    def fn(audio, **kw):
        fake.offset = windows[len(fake.calls)][0]
        return fake(audio, **kw)

    progress = []
    segs = stt_service.transcribe(long_wav, initial_prompt="용어", on_progress=lambda i, n: progress.append((i, n)), transcribe_fn=fn)
    assert len(fake.calls) == len(windows) == 4
    assert progress == [(0, 4), (1, 4), (2, 4), (3, 4)]
    assert all(c["language"] == "ko" and c["condition_on_previous_text"] is False and c["initial_prompt"] == "용어" for c in fake.calls)
    assert [s.start for s in segs] == [3.0, 12.0, 920.0, 1820.0, 1840.0]  # absolute timestamps, no duplicates


def test_load_wav_rejects_wrong_format(tmp_path):
    p = tmp_path / "stereo.wav"
    subprocess.run([find_binary("ffmpeg"), "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", "-ac", "2", "-ar", "44100", str(p)], check=True)
    with pytest.raises(stt_service.STTError):
        stt_service.load_wav16k(p)
