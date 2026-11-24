"""Test setup: an isolated SQLite DB + storage dir, set BEFORE the app is imported."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="lawa-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["STORAGE_DIR"] = str(_TMP / "storage")
os.environ["LOG_DIR"] = str(_TMP / "logs")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.session import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.media import find_binary  # noqa: E402


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_state():
    """Fresh tables and empty storage for every test."""
    import app.models  # noqa: F401

    Base.metadata.drop_all(engine)
    init_db()
    storage = get_settings().storage_dir
    shutil.rmtree(storage, ignore_errors=True)
    storage.mkdir(parents=True)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture(scope="session")
def media_dir() -> Path:
    """Real audio/video files generated with ffmpeg (3 s, 440 Hz tone)."""
    d = _TMP / "media"
    d.mkdir(exist_ok=True)
    ff = find_binary("ffmpeg")
    tone = ["-f", "lavfi", "-i", "sine=frequency=440:duration=3"]
    jobs = {
        "tone.wav": [*tone, "-ac", "2", "-ar", "44100"],
        "tone.mp3": [*tone, "-c:a", "libmp3lame", "-b:a", "64k"],
        "tone.m4a": [*tone, "-c:a", "aac", "-b:a", "64k"],
        "clip.mp4": ["-f", "lavfi", "-i", "testsrc=duration=3:size=160x120:rate=10", *tone, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"],
        "silent_video.mp4": ["-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p"],
    }
    for name, args in jobs.items():
        subprocess.run([ff, "-nostdin", "-loglevel", "error", "-y", *args, str(d / name)], check=True)
    return d


def make_meeting(client: TestClient, **overrides) -> dict:
    body = {
        "title": "테스트 회의",
        "meeting_date": "2026-11-20",
        "attendees": ["김민수", "이지은"],
        "purpose": "검증",
        "agenda": ["상품설명서 검증", "오류 조치"],
        "instructions": "",
    } | overrides
    r = client.post("/api/meetings", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def upload(client: TestClient, meeting_id: str, path: Path, filename: str | None = None, mime: str = "application/octet-stream"):
    with path.open("rb") as f:
        return client.post(f"/api/meetings/{meeting_id}/audio", files={"file": (filename or path.name, f, mime)})
