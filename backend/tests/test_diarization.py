import os

import pytest

from app.config import get_settings
from app.services import diarization_service as d
from app.services import llm_service, stt_service
from app.services.diarization_service import Turn
from app.services.stt_service import Segment
from tests.conftest import make_meeting, upload
from tests.fakes import FakeLLM
from worker.main import run_once


def test_telemetry_is_disabled_before_pyannote_import():
    assert os.environ["PYANNOTE_METRICS_ENABLED"] == "false"
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"


def W(word, start, end):
    return {"word": word, "start": start, "end": end}


def test_segments_without_words_use_overlap_and_gap():
    segs = [Segment(0, 2, "a"), Segment(10, 11, "b"), Segment(30, 31, "c")]
    turns = [Turn(0, 1.5, "X"), Turn(11.5, 12, "Y")]
    assert d.assign_speakers(segs, turns) == ["X", "Y", None]  # b: within 1 s gap; c: too far


def test_display_labels_number_by_first_appearance():
    assert d.display_labels(["SPEAKER_03", None, "SPEAKER_00", "SPEAKER_03"]) == ["화자 1", None, "화자 2", "화자 1"]


@pytest.fixture
def engines(monkeypatch):
    """Whisper with word timings + fake diarizer (two speakers) + fake LLM."""
    def whisper(audio, **kw):
        assert kw["word_timestamps"] is True
        return {"segments": [
            {"start": 0.0, "end": 4.0, "text": "약관 최종본은 누가 요청할까요?", "words": [W(" 약관", 0, 0.8), W(" 최종본은", 0.8, 1.6), W(" 누가", 1.6, 2.4), W(" 요청할까요?", 2.4, 4.0)]},
            {"start": 4.5, "end": 9.0, "text": "제가 내일까지 요청하겠습니다.", "words": [W(" 제가", 4.5, 5.2), W(" 내일까지", 5.2, 6.5), W(" 요청하겠습니다.", 6.5, 9.0)]},
        ]}

    def diarizer(wav):
        return [Turn(0.0, 4.2, "SPEAKER_01"), Turn(4.3, 9.5, "SPEAKER_00")]

    final = {
        "meeting_summary": "화자 2가 내일까지 약관 최종본을 요청하기로 함",
        "action_items": [{"task": "약관 최종본 요청", "assignee": "화자 2", "deadline": "내일까지", "evidence": "제가 내일까지 요청하겠습니다", "timestamp": "00:00:04"}],
        "discussion_items": [{"topic": "약관", "content": "화자 1이 질문", "speaker": "화자 1", "timestamp": "00:00:00"}],
    }
    from app.agents.llm_schemas import FinalMinutes

    llm = FakeLLM(FinalMinutes.model_validate(final))
    monkeypatch.setattr(get_settings(), "diarization_enabled", True)
    monkeypatch.setattr(stt_service, "_mlx_transcribe", whisper)
    monkeypatch.setattr(d, "diarize", diarizer)
    monkeypatch.setattr(d, "unload", lambda: None)
    monkeypatch.setattr(llm_service, "chat_json", llm)
    return llm


def test_pipeline_labels_speakers_and_naming_updates_minutes(client, media_dir, engines):
    llm = engines
    m = make_meeting(client, attendees=["김민수 과장", "박정우 책임"])
    upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    client.post(f"/api/meetings/{m['id']}/analyze")
    run_once("w")

    t = client.get(f"/api/meetings/{m['id']}/transcript").json()
    assert [(s["speaker"], s["text"]) for s in t["segments"]] == [("화자 1", "약관 최종본은 누가 요청할까요?"), ("화자 2", "제가 내일까지 요청하겠습니다.")]
    assert "words" not in t["segments"][0]
    assert "[00:00:04] 화자 2: 제가 내일까지" in llm.calls[0]["user"]

    mn = client.get(f"/api/meetings/{m['id']}/minutes").json()
    assert mn["action_items"][0]["assignee"] == "화자 2"  # speaker of "제가 하겠습니다" is accepted
    assert mn["discussion_items"][0]["speaker"] == "화자 1"

    # Name the speakers: transcript stays raw, minutes and later analyses use names.
    r = client.put(f"/api/meetings/{m['id']}/speakers", json={"names": {"화자 1": "김민수 과장", "화자 2": "박정우 책임"}})
    assert r.status_code == 200 and r.json()["speaker_names"] == {"화자 1": "김민수 과장", "화자 2": "박정우 책임"}
    mn = client.get(f"/api/meetings/{m['id']}/minutes").json()
    assert mn["action_items"][0]["assignee"] == "박정우 책임"
    assert mn["meeting_summary"].startswith("박정우 책임이 ")  # particle fixed (가 → 이)
    assert mn["discussion_items"][0]["speaker"] == "김민수 과장"

    # Renaming again replaces the previous names.
    client.put(f"/api/meetings/{m['id']}/speakers", json={"names": {"화자 2": "이지은 대리"}})
    mn = client.get(f"/api/meetings/{m['id']}/minutes").json()
    assert mn["action_items"][0]["assignee"] == "이지은 대리"
    assert mn["discussion_items"][0]["speaker"] == "화자 1"

    # Re-analysis (LLM only) sends the names to the model.
    client.post(f"/api/meetings/{m['id']}/analyze")
    run_once("w")
    assert "이지은 대리: 제가 내일까지" in llm.calls[-1]["user"]

    assert client.put(f"/api/meetings/{m['id']}/speakers", json={"names": {"화자 9": "누구"}}).status_code == 422
    assert client.put(f"/api/meetings/{m['id']}/speakers", json={"names": {"화자 1": "줄\n바꿈"}}).status_code == 422


def test_diarization_failure_does_not_fail_the_meeting(client, media_dir, engines, monkeypatch):
    def broken(wav):
        raise d.DiarizationError("모델 없음 (테스트)")

    monkeypatch.setattr(d, "diarize", broken)
    m = make_meeting(client)
    upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    job = client.post(f"/api/meetings/{m['id']}/analyze").json()
    run_once("w")
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "COMPLETED"
    t = client.get(f"/api/meetings/{m['id']}/transcript").json()
    assert all(s["speaker"] is None for s in t["segments"])
    mn = client.get(f"/api/meetings/{m['id']}/minutes").json()
    assert any("화자 분리를 건너뛰었습니다" in n for n in mn["review_notes"])


def test_rename_does_not_touch_longer_labels():
    from app.services.meeting_service import _rename

    assert _rename("화자 1과 화자 10", {"화자 1": "김"}) == "김과 화자 10"
    assert _rename("화자 2가 맡고 화자 2는 보고", {"화자 2": "이지은 대리"}) == "이지은 대리가 맡고 이지은 대리는 보고"
    assert _rename("화자 2가 화자 2를", {"화자 2": "박정우 책임"}) == "박정우 책임이 박정우 책임을"
    assert _rename("화자 2가요", {"화자 2": "박정우 책임"}) == "박정우 책임가요"  # not a particle → untouched


def test_processes_run_model_libraries_offline():
    import app.offline  # noqa: F401
    import huggingface_hub.constants as c

    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert c.HF_HUB_OFFLINE is True  # read at import time — proves app.offline ran first


def test_speaker_label_is_not_flagged_as_a_number():
    from app.agents import review_agent
    from app.agents.llm_schemas import FinalMinutes

    segs = [Segment(0, 3, "제가 하겠습니다", speaker="화자 2")]
    r = review_agent.review(FinalMinutes(meeting_summary="화자 2가 맡기로 함"), segs, [], duration=3)
    assert not any("수치" in n for n in r.notes)
