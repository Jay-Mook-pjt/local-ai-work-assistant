from datetime import date

from app.agents import meeting_agent, review_agent, task_agent
from app.agents.llm_schemas import ChunkAnalysis, FinalMinutes
from app.config import get_settings
from app.models import AudioFile, Meeting
from app.schemas.meeting import ActionItemIn
from app.services.stt_service import Segment
from tests.fakes import FINAL, TRANSCRIPT, FakeLLM

SEGMENTS = [Segment(**s) for s in TRANSCRIPT]
AGENDA = ["상품설명서 검증", "오류 조치", "예산 검토"]


def _meeting() -> Meeting:
    m = Meeting(id="a" * 32, title="방카 테스트 자동화 회의", meeting_date=date(2026, 11, 20), attendees=["김민수 과장", "이지은 대리"],
                purpose="진행 점검", agenda=AGENDA, instructions="담당자별 업무 중심으로")
    m.audio = AudioFile(original_filename="a.wav", stored_path="x", size_bytes=1, mime_type="audio/wav", duration_seconds=1900)
    return m


def test_review_grounds_decisions_and_actions():
    r = review_agent.review(FINAL, SEGMENTS, AGENDA, duration=1900)
    m = r.minutes
    # Verified decision keeps content; timestamp comes from the transcript, not the LLM.
    assert [d.content for d in m.decisions] == ["12월 둘째 주까지 전 상품 자동화 적용"]
    assert m.decisions[0].timestamp == "00:30:20"
    # Fabricated decision is not presented as a decision.
    assert any("[검증 필요] 예산 2억 증액" in x for x in m.open_issues)

    a1, a2 = m.action_items
    assert (a1.assignee, a1.deadline, a1.timestamp) == ("이지은", "이번 주 금요일", "00:15:20")
    # Assignee/deadline never mentioned in the meeting → 미확인; no evidence → flagged.
    assert (a2.assignee, a2.deadline, a2.timestamp) == ("미확인", "미확인", "미확인")
    assert a2.task.startswith("[검증 필요]")
    # No diarisation → speaker is always 미확인.
    assert {d.speaker for d in m.discussion_items} == {"미확인"}
    # Agenda item never discussed is reported explicitly.
    assert any(d.topic == "예산 검토" and "확인되지 않았습니다" in d.content for d in m.discussion_items)
    assert len(r.notes) >= 4


def test_review_accepts_paraphrased_evidence():
    seg = review_agent.Grounding(SEGMENTS).locate("이지은 대리님이 금요일까지 오류 항목 재검증하기로")
    assert seg is not None and seg.start == 920.0


def test_deadline_tokens_must_appear():
    g = review_agent.Grounding(SEGMENTS)
    assert review_agent.check_deadline("12월 둘째 주", g, "") == "12월 둘째 주"
    assert review_agent.check_deadline("2026-11-27 (금요일)", g, "") == "미확인"  # computed date not in transcript
    assert review_agent.check_deadline("미확인", g, "") == "미확인"


def test_task_agent_aligns_attendees_and_merges_duplicates():
    items = [
        ActionItemIn(task="오류 항목 재검증", assignee="이지은", deadline="미확인"),
        ActionItemIn(task="오류 항목을 재검증", assignee="미확인", deadline="금요일", evidence="근거", timestamp="00:15:20"),
        ActionItemIn(task="최종본 요청", assignee="김민수"),
    ]
    out = task_agent.normalize(items, ["김민수 과장", "이지은 대리"])
    assert [(i.task, i.assignee, i.deadline) for i in out] == [("오류 항목 재검증", "이지은 대리", "금요일"), ("최종본 요청", "김민수 과장", "미확인")]
    assert out[0].evidence == "근거"


def test_chunk_transcript_splits_on_segments_with_context():
    segs = [Segment(i * 10, i * 10 + 5, f"문장 {i} " + "가" * 50) for i in range(40)]
    chunks = meeting_agent.chunk_transcript(segs, max_chars=700)
    assert len(chunks) > 3
    assert all(len(c) <= 700 + 200 for c in chunks)  # context lines may add a little
    assert chunks[1].startswith("(이전 구간에서 이어짐)")
    body = "\n".join(c for c in chunks)
    assert all(f"문장 {i} " in body for i in range(40))


def test_analyze_short_meeting_uses_single_call():
    llm = FakeLLM()
    res = meeting_agent.analyze(_meeting(), SEGMENTS, model="qwen3:14b", chat=llm)
    assert len(llm.calls) == 1 and llm.calls[0]["schema"] is FinalMinutes
    prompt = llm.calls[0]["user"]
    assert "방카 테스트 자동화 회의" in prompt and "1. 상품설명서 검증" in prompt and "담당자별 업무 중심으로" in prompt
    assert "[00:15:20] 이지은 대리님이" in prompt
    assert "미확인" in llm.calls[0]["system"]
    assert res.model == "qwen3:14b" and res.llm_calls == 1
    assert res.minutes.action_items[0].assignee == "이지은 대리"  # aligned with attendee


def test_analyze_long_meeting_maps_then_merges(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_chunk_chars", 1000)
    segs = [Segment(i * 30, i * 30 + 20, f"{i}번째 발언입니다 " + "내용 " * 30) for i in range(30)]
    llm = FakeLLM()
    stages = []
    meeting_agent.analyze(_meeting(), segs, chat=llm, on_progress=lambda st, i, n: stages.append(st))
    schemas = [c["schema"] for c in llm.calls]
    assert schemas[:-1] == [ChunkAnalysis] * (len(schemas) - 1) and schemas[-1] is FinalMinutes
    assert len(schemas) >= 4
    assert '"구간": 1' in llm.calls[-1]["user"]  # merge sees chunk extracts, not the transcript
    assert "번째 발언입니다" not in llm.calls[-1]["user"]
    assert stages[0] == "ANALYZING" and stages[-1] == "GENERATING"


def test_analyze_rejects_empty_transcript():
    import pytest

    from app.services.llm_service import LLMError

    with pytest.raises(LLMError):
        meeting_agent.analyze(_meeting(), [], chat=FakeLLM())


def test_task_assignment_is_not_also_a_decision():
    final = FINAL.model_copy(deep=True)
    final.decisions.append(final.decisions[0].model_copy(update={"content": "이지은 대리가 금요일까지 재검증한다", "evidence": final.action_items[0].evidence}))
    r = review_agent.review(final, SEGMENTS, [], duration=1900)
    assert [d.content for d in r.minutes.decisions] == ["12월 둘째 주까지 전 상품 자동화 적용"]
    assert any("업무 배정" in n for n in r.notes)


def test_open_issue_unknown_suffix_is_removed():
    final = FINAL.model_copy(update={"open_issues": ["테스트 서버 증설 예산 확인 미확인", "보고서 담당자 (미확인)"]})
    r = review_agent.review(final, SEGMENTS, [], duration=1900)
    assert r.minutes.open_issues[:2] == ["테스트 서버 증설 예산 확인", "보고서 담당자"]


def test_misheard_attendee_name_is_corrected_but_evidence_kept():
    segs = [Segment(60, 66, "좋습니다. 이지훈 대리님이 금요일까지 재검증해 주시는 걸로 하겠습니다.")]
    final = FinalMinutes(
        meeting_summary="이지훈 대리가 재검증을 맡았다.",
        action_items=[{"task": "오류 재검증", "assignee": "이지훈 대리", "deadline": "금요일", "evidence": "이지훈 대리님이 금요일까지 재검증해 주시는 걸로 하겠습니다", "timestamp": "00:01:00"}],
    )
    m = _meeting()
    m.agenda = []
    res = meeting_agent.analyze(m, segs, chat=FakeLLM(final))
    a = res.minutes.action_items[0]
    assert a.assignee == "이지은 대리"
    assert "이지훈" in a.evidence  # quote stays verbatim
    assert "이지은 대리가" in res.minutes.meeting_summary
    assert any("보정" in n for n in res.notes)


def test_attendee_name_written_correctly_by_llm_is_accepted():
    g = review_agent.Grounding([Segment(0, 5, "이지훈 대리님이 금요일까지 하기로")])
    assert review_agent.check_assignee("이지은 대리", g, "", ["이지은 대리"]) == "이지은 대리"
    assert review_agent.check_assignee("이지은 대리", g, "", []) == "미확인"  # not an attendee → no leniency
    assert review_agent.check_assignee("박정우", g, "", ["박정우 책임"]) == "미확인"  # never mentioned


def test_name_correction_requires_unique_one_char_match():
    from app.agents.task_agent import misheard_attendee

    assert misheard_attendee("이지훈 대리", ["이지은 대리", "김민수"]) == "이지은 대리"
    assert misheard_attendee("이지훈", ["이지은", "이지운"]) is None  # ambiguous
    assert misheard_attendee("박지훈", ["이지은"]) is None  # different surname
    assert misheard_attendee("이지은", ["이지은 대리"]) is None  # already correct


def test_invented_numbers_are_reported():
    final = FINAL.model_copy(update={"meeting_summary": "12개 중 9개 검증 완료, 23건 중 21건 수정 완료(90%)."})
    segs = SEGMENTS + [Segment(50, 55, "오류 23건이 있었습니다.")]
    r = review_agent.review(final, segs, [], duration=1900, meeting_info="회의 2026-11-20")
    num_notes = [n for n in r.notes if "수치" in n]
    assert len(num_notes) == 1 and "21" in num_notes[0] and "90" in num_notes[0]
    assert "12" not in num_notes[0].split("수치")[1].split("은(는)")[0].replace("21", "").replace("90", "")


def test_korean_numerals_count_as_grounded():
    from app.agents.review_agent import korean_numbers

    assert {"12", "9"} <= korean_numbers("열두 개 중 아홉 개 검증이 끝났습니다")
    assert "23" in korean_numbers("오류 스물세 건")
    assert "12" in korean_numbers("십이월 둘째 주")
    assert "23" in korean_numbers("이십삼 건")
    assert "2" not in korean_numbers("이 문제는 사실 오늘 논의")  # 이/사/오 as words are ignored


def test_decision_naming_an_assignee_is_treated_as_assignment():
    final = FINAL.model_copy(deep=True)
    # Grounded on a different utterance than the action item, but names its assignee.
    final.decisions.append(final.decisions[0].model_copy(update={"content": "이지은 대리님이 금요일까지 재검증하는 걸로 함", "evidence": "상품설명서는 열두 개 중 아홉 개 검증이 끝났습니다"}))
    r = review_agent.review(final, SEGMENTS, [], duration=1900)
    assert [d.content for d in r.minutes.decisions] == ["12월 둘째 주까지 전 상품 자동화 적용"]
