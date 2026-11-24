"""Deterministic stand-ins for MLX Whisper and Ollama used by pipeline tests."""

from app.agents.llm_schemas import ChunkAnalysis, FinalMinutes
from app.services.llm_service import CallStats

TRANSCRIPT = [
    {"start": 3.0, "end": 9.0, "text": "오늘 안건은 상품설명서 검증과 오류 조치입니다."},
    {"start": 12.0, "end": 20.0, "text": "상품설명서는 열두 개 중 아홉 개 검증이 끝났습니다."},
    {"start": 920.0, "end": 930.0, "text": "이지은 대리님이 이번 주 금요일까지 오류 항목을 재검증하기로 하죠."},
    {"start": 1820.0, "end": 1830.0, "text": "자동화 일정은 12월 둘째 주까지 전 상품 적용으로 확정하겠습니다."},
    {"start": 1840.0, "end": 1850.0, "text": "테스트 서버 증설은 다음 회의에서 다시 논의하죠."},
]


class FakeWhisper:
    """Returns TRANSCRIPT segments that fall inside the requested window."""

    def __init__(self, segments=TRANSCRIPT, sample_rate=16000):
        self.segments = segments
        self.sr = sample_rate
        self.calls: list[dict] = []
        self.offset = 0.0

    def __call__(self, audio, **kwargs):
        self.calls.append(kwargs)
        length = len(audio) / self.sr
        start = self.offset
        out = [
            {"start": s["start"] - start, "end": s["end"] - start, "text": s["text"], "no_speech_prob": 0.01, "avg_logprob": -0.2, "compression_ratio": 1.2}
            for s in self.segments
            if start <= (s["start"] + s["end"]) / 2 < start + length
        ]
        return {"segments": out}


STATS = CallStats(model="fake", seconds=0.1, load_seconds=0, prompt_tokens=100, output_tokens=50, tokens_per_second=500)

FINAL = FinalMinutes(
    meeting_summary="9개 상품 검증 완료, 12월 둘째 주 전 상품 자동화 적용 확정.",
    discussion_items=[{"topic": "상품설명서 검증", "content": "12개 중 9개 검증 완료", "speaker": "김민수", "timestamp": "00:00:12"}],
    decisions=[
        {"content": "12월 둘째 주까지 전 상품 자동화 적용", "evidence": "자동화 일정은 12월 둘째 주까지 전 상품 적용으로 확정하겠습니다", "timestamp": "00:00:00"},
        {"content": "예산 2억 증액", "evidence": "예산을 2억 늘리기로 했습니다", "timestamp": "00:10:00"},  # fabricated
    ],
    action_items=[
        {"task": "오류 항목 재검증", "assignee": "이지은", "deadline": "이번 주 금요일", "evidence": "이지은 대리님이 이번 주 금요일까지 오류 항목을 재검증하기로 하죠", "timestamp": "00:00:01"},
        {"task": "고객사 최종본 요청", "assignee": "박정우", "deadline": "11월 30일", "evidence": "", "timestamp": "미확인"},  # ungrounded
    ],
    open_issues=["테스트 서버 증설 여부"],
    next_meeting_checks=["테스트 서버 증설 결정"],
)


class FakeLLM:
    """Records prompts; returns FINAL for final schemas and an empty extract per chunk."""

    def __init__(self, final: FinalMinutes = FINAL):
        self.final = final
        self.calls: list[dict] = []

    def __call__(self, *, system, user, schema, model=None, purpose=""):
        self.calls.append({"system": system, "user": user, "schema": schema, "model": model, "purpose": purpose})
        if schema is ChunkAnalysis:
            return ChunkAnalysis(decisions=self.final.decisions, action_items=self.final.action_items), STATS
        return self.final.model_copy(deep=True), STATS
