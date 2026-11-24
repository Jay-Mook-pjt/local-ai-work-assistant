import json
import subprocess

from app.config import get_settings
from app.models import Job
from app.services import job_service
from app.services.media import find_binary
from tests.conftest import make_meeting, upload
from worker.main import run_once


def test_analyze_requires_audio(client):
    m = make_meeting(client)
    r = client.post(f"/api/meetings/{m['id']}/analyze")
    assert r.status_code == 409 and "음성 파일" in r.json()["detail"]


def test_analyze_queues_job_and_rejects_duplicates(client, media_dir):
    m = make_meeting(client)
    upload(client, m["id"], media_dir / "tone.m4a", mime="audio/mp4")
    r = client.post(f"/api/meetings/{m['id']}/analyze")
    assert r.status_code == 202
    job = r.json()
    assert job["status"] == "PENDING"
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "PENDING"
    meeting = client.get(f"/api/meetings/{m['id']}").json()
    assert meeting["latest_job_id"] == job["id"] and meeting["status"] == "PENDING"

    assert client.post(f"/api/meetings/{m['id']}/analyze").status_code == 409
    # Re-upload is blocked while a job is queued/running.
    assert upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav").status_code == 409


def test_claim_is_exclusive(client, db, media_dir):
    m = make_meeting(client)
    upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    client.post(f"/api/meetings/{m['id']}/analyze")
    first = job_service.claim_next(db, "w1")
    assert first is not None and first.status == "PREPROCESSING" and first.worker_id == "w1"
    assert job_service.claim_next(db, "w2") is None


def test_worker_preprocesses_then_stops_before_stt(client, media_dir):
    """PHASE 3: conversion runs for real; STT is not connected yet (PHASE 4)."""
    m = make_meeting(client)
    upload(client, m["id"], media_dir / "clip.mp4", mime="video/mp4")  # video container → audio extracted
    job_id = client.post(f"/api/meetings/{m['id']}/analyze").json()["id"]

    assert run_once("test-worker") is True
    assert run_once("test-worker") is False  # queue is empty

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "FAILED"
    assert "PHASE 4" in job["error"] and "오디오 변환까지는 정상 완료" in job["error"]
    assert client.get(f"/api/meetings/{m['id']}").json()["status"] == "FAILED"

    processed = list((get_settings().storage_dir / "audio/processed" / m["id"]).glob("*.wav"))
    assert len(processed) == 1
    probe = subprocess.run(
        [find_binary("ffprobe"), "-v", "error", "-print_format", "json", "-show_streams", str(processed[0])],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert (stream["codec_name"], stream["sample_rate"], stream["channels"]) == ("pcm_s16le", "16000", 1)

    # A failed job can be retried.
    retry = client.post(f"/api/meetings/{m['id']}/analyze")
    assert retry.status_code == 202 and retry.json()["id"] != job_id


def test_missing_source_file_fails_cleanly(client, media_dir):
    m = make_meeting(client)
    upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    for f in (get_settings().storage_dir / "audio/original" / m["id"]).iterdir():
        f.unlink()
    job_id = client.post(f"/api/meetings/{m['id']}/analyze").json()["id"]
    run_once("w")
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "FAILED" and "원본 음성 파일" in job["error"]


def test_interrupted_jobs_are_failed_on_worker_start(client, db, media_dir):
    m = make_meeting(client)
    upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    client.post(f"/api/meetings/{m['id']}/analyze")
    job = job_service.claim_next(db, "dead-worker")
    job_service.set_progress(db, job, "TRANSCRIBING", 40, "음성 인식 중")

    assert job_service.fail_interrupted(db) == 1
    db.refresh(job)
    assert job.status == "FAILED" and "중단" in job.error
    assert db.get(Job, job.id).status == "FAILED"


def test_job_not_found(client):
    assert client.get("/api/jobs/" + "a" * 32).status_code == 404
    assert client.get("/api/jobs/not-an-id").status_code == 422
