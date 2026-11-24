import pytest

from app.services import llm_service, stt_service
from tests.conftest import make_meeting, upload
from tests.fakes import TRANSCRIPT, FakeLLM
from worker.main import run_once

RPA = {"term": "RPA", "description": "온프레미스(서버·개발도구·수행봇)로 구성된 업무 자동화", "aliases": ["알피에이"]}
RDA = {"term": "RDA", "description": "개인 업무 PC에서 로컬 개인 비서처럼 돌리는 자동화 도구", "aliases": []}


def test_crud_and_validation(client):
    r = client.post("/api/glossary", json=RPA | {"aliases": [" 알피에이 ", "알피에이", ""]})
    assert r.status_code == 201
    t = r.json()
    assert t["aliases"] == ["알피에이"]
    assert client.post("/api/glossary", json=RPA | {"term": "rpa"}).status_code == 409  # case-insensitive duplicate
    assert client.post("/api/glossary", json={"term": "   "}).status_code == 422
    client.post("/api/glossary", json=RDA)
    assert [x["term"] for x in client.get("/api/glossary").json()] == ["RDA", "RPA"]

    upd = client.put(f"/api/glossary/{t['id']}", json=RPA | {"description": "수정된 설명"}).json()
    assert upd["description"] == "수정된 설명"
    assert client.put(f"/api/glossary/{t['id']}", json=RDA).status_code == 409  # rename onto existing term
    assert client.delete(f"/api/glossary/{t['id']}").status_code == 204
    assert client.delete(f"/api/glossary/{t['id']}").status_code == 404
    assert [x["term"] for x in client.get("/api/glossary").json()] == ["RDA"]


@pytest.fixture
def engines(monkeypatch):
    calls: list[dict] = []

    def whisper(audio, **kw):
        calls.append(kw)
        return {"segments": [dict(s, no_speech_prob=0.0, avg_logprob=-0.1, compression_ratio=1.1) for s in TRANSCRIPT]}

    llm = FakeLLM()
    monkeypatch.setattr(stt_service, "_mlx_transcribe", whisper)
    monkeypatch.setattr(llm_service, "chat_json", llm)
    return calls, llm


def test_glossary_reaches_stt_and_llm(client, media_dir, engines):
    stt_calls, llm = engines
    client.post("/api/glossary", json=RPA)
    client.post("/api/glossary", json=RDA)
    m = make_meeting(client, attendees=["이지은 대리"])
    upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    client.post(f"/api/meetings/{m['id']}/analyze")
    run_once("w")

    prompt = stt_calls[0]["initial_prompt"]
    assert "RPA" in prompt and "RDA" in prompt and "이지은 대리" in prompt and len(prompt) <= 300
    system = llm.calls[0]["system"]
    assert "# 프로젝트 용어집" in system
    assert "- RPA: 온프레미스(서버·개발도구·수행봇)로 구성된 업무 자동화 (음성 인식 시 '알피에이'(으)로 들릴 수 있음)" in system
    assert "- RDA: 개인 업무 PC에서" in system
    assert "추가하지 않는다" in system  # glossary must not become a content source


def test_no_glossary_section_when_empty(client, media_dir, engines):
    _, llm = engines
    m = make_meeting(client)
    upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    client.post(f"/api/meetings/{m['id']}/analyze")
    run_once("w")
    assert "용어집" not in llm.calls[0]["system"]


def test_retranscribe_option_reruns_stt(client, media_dir, engines):
    stt_calls, _ = engines
    m = make_meeting(client)
    upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    client.post(f"/api/meetings/{m['id']}/analyze")
    run_once("w")
    client.post(f"/api/meetings/{m['id']}/analyze")  # default: transcript reused
    run_once("w")
    assert len(stt_calls) == 1
    job = client.post(f"/api/meetings/{m['id']}/analyze", json={"retranscribe": True}).json()
    assert job["retranscribe"] is True
    run_once("w")
    assert len(stt_calls) == 2
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "COMPLETED"
