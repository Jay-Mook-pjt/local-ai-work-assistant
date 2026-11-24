import json
import subprocess

import pytest

from app.config import get_settings
from app.models import Job
from app.services import job_service
from app.services.media import find_binary
from tests.conftest import make_meeting, upload
from tests.fakes import TRANSCRIPT, FakeLLM
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


@pytest.fixture
def engines(monkeypatch):
    """Fake Whisper (all TRANSCRIPT segments) + fake Ollama, wired into the real pipeline."""
    from app.services import llm_service, stt_service

    calls = {"stt": 0}

    def whisper(audio, **kw):
        calls["stt"] += 1
        return {"segments": [dict(s, no_speech_prob=0.0, avg_logprob=-0.1, compression_ratio=1.1) for s in TRANSCRIPT]}

    llm = FakeLLM()
    monkeypatch.setattr(stt_service, "_mlx_transcribe", whisper)
    monkeypatch.setattr(llm_service, "chat_json", llm)
    monkeypatch.setattr(llm_service, "installed_models", lambda: ["qwen3:14b", "exaone3.5:7.8b"])
    return calls, llm


def test_full_pipeline_produces_grounded_minutes(client, media_dir, engines):
    stt_calls, llm = engines
    m = make_meeting(client, attendees=["이지은 대리"])
    upload(client, m["id"], media_dir / "clip.mp4", mime="video/mp4")  # video container → audio extracted
    job_id = client.post(f"/api/meetings/{m['id']}/analyze").json()["id"]

    assert run_once("test-worker") is True
    assert run_once("test-worker") is False  # queue is empty

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "COMPLETED" and job["progress"] == 100, job
    assert "검토가 필요한 항목" in job["message"] and job["llm_model"] == "qwen3:14b"
    assert client.get(f"/api/meetings/{m['id']}").json()["status"] == "COMPLETED"

    processed = list((get_settings().storage_dir / "audio/processed" / m["id"]).glob("*.wav"))
    stream = json.loads(subprocess.run(
        [find_binary("ffprobe"), "-v", "error", "-print_format", "json", "-show_streams", str(processed[0])],
        capture_output=True, text=True, check=True,
    ).stdout)["streams"][0]
    assert (stream["codec_name"], stream["sample_rate"], stream["channels"]) == ("pcm_s16le", "16000", 1)

    t = client.get(f"/api/meetings/{m['id']}/transcript").json()
    assert len(t["segments"]) == len(TRANSCRIPT) and t["model"] == get_settings().stt_model
    assert (get_settings().storage_dir / "transcripts" / m["id"] / "transcript.txt").exists()

    minutes = client.get(f"/api/meetings/{m['id']}/minutes").json()
    assert minutes["llm_model"] == "qwen3:14b" and minutes["edited"] is False
    assert [d["timestamp"] for d in minutes["decisions"]] == ["00:30:20"]
    assert minutes["action_items"][0]["assignee"] == "이지은 대리"
    assert any(x.startswith("[검증 필요]") for x in minutes["open_issues"])
    assert any("결정사항 근거 없음" in n for n in minutes["review_notes"])
    # Content search now reaches the transcript.
    assert [x["id"] for x in client.get("/api/meetings", params={"q": "아홉 개"}).json()] == [m["id"]]
    assert stt_calls["stt"] == 1


def test_reanalysis_reuses_transcript_and_protects_edits(client, media_dir, engines):
    stt_calls, llm = engines
    m = make_meeting(client)
    upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    client.post(f"/api/meetings/{m['id']}/analyze")
    run_once("w")
    minutes = client.get(f"/api/meetings/{m['id']}/minutes").json()
    client.put(f"/api/meetings/{m['id']}/minutes", json=minutes | {"meeting_summary": "직접 고친 요약"})

    r = client.post(f"/api/meetings/{m['id']}/analyze", json={"llm_model": "exaone3.5:7.8b"})
    assert r.status_code == 409 and "수정한 회의록" in r.json()["detail"]
    assert client.post(f"/api/meetings/{m['id']}/analyze", json={"llm_model": "not-installed:1b", "overwrite_edited": True}).status_code == 422

    r = client.post(f"/api/meetings/{m['id']}/analyze", json={"llm_model": "exaone3.5:7.8b", "overwrite_edited": True})
    assert r.status_code == 202 and r.json()["llm_model"] == "exaone3.5:7.8b"
    run_once("w")
    assert stt_calls["stt"] == 1  # transcript reused
    assert llm.calls[-1]["model"] == "exaone3.5:7.8b"
    after = client.get(f"/api/meetings/{m['id']}/minutes").json()
    assert after["llm_model"] == "exaone3.5:7.8b" and after["edited"] is False


def test_llm_failure_is_reported_and_retryable(client, media_dir, engines, monkeypatch):
    from app.services import llm_service

    def down(**kw):
        raise llm_service.LLMError("Ollama에 연결할 수 없습니다 (테스트).")

    monkeypatch.setattr(llm_service, "chat_json", down)
    m = make_meeting(client)
    upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    job_id = client.post(f"/api/meetings/{m['id']}/analyze").json()["id"]
    run_once("w")
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "FAILED" and "Ollama" in job["error"]
    assert client.get(f"/api/meetings/{m['id']}/transcript").json() is not None  # STT result kept
    assert client.post(f"/api/meetings/{m['id']}/analyze").status_code == 202


def test_settings_default_model(client, engines):
    s = client.get("/api/settings").json()
    assert s["llm_model"] == get_settings().llm_model and s["llm_model_source"] == "env"
    assert "exaone3.5:7.8b" in s["available_models"]
    assert client.put("/api/settings", json={"llm_model": "nope:1b"}).status_code == 422
    s = client.put("/api/settings", json={"llm_model": "exaone3.5:7.8b"}).json()
    assert (s["llm_model"], s["llm_model_source"]) == ("exaone3.5:7.8b", "user")


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
