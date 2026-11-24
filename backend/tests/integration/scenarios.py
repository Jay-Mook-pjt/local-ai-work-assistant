"""Synthetic meetings with known ground truth.

Each line is (speaker, text). Lines marked with a fact id (third element) are the
"planted" facts the grader looks for; their audio start time becomes the
expected timestamp.
"""

import random
from dataclasses import dataclass, field


@dataclass
class Expect:
    decisions: list[dict] = field(default_factory=list)  # {"id", "keywords"}
    not_decisions: list[dict] = field(default_factory=list)  # {"id", "keywords"} must NOT be a decision
    actions: list[dict] = field(default_factory=list)  # {"id", "keywords", "assignee", "deadline"}
    unassigned: list[dict] = field(default_factory=list)  # {"id", "keywords"} task without owner
    open_items: list[dict] = field(default_factory=list)  # {"id", "keywords"} in open issues / next checks


@dataclass
class Scenario:
    name: str
    title: str
    meeting_date: str
    attendees: list[str]
    purpose: str
    agenda: list[str]
    instructions: str
    lines: list[tuple]  # (speaker, text[, fact_id])
    expect: Expect


INSTRUCTIONS = "담당자별 업무와 후속 조치를 중심으로 정리해 줘. 결정사항과 단순 논의사항을 구분하고, 다음 회의에서 확인해야 할 내용도 별도로 작성해 줘."

# --------------------------------------------------------------------------- short

SHORT = Scenario(
    name="short",
    title="방카슈랑스 테스트 자동화 주간 회의",
    meeting_date="2026-11-24",
    attendees=["김민수 과장", "박정우 책임", "이지은 대리"],
    purpose="테스트 자동화 진행 현황 점검",
    agenda=["상품설명서 검증 진행사항", "CheckMATE 테스트 오류 조치", "향후 테스트 자동화 일정"],
    instructions=INSTRUCTIONS,
    lines=[
        ("A", "안녕하세요. 지금부터 방카슈랑스 테스트 자동화 주간 회의를 시작하겠습니다. 오늘 안건은 세 가지입니다. 첫째 상품설명서 검증 진행사항, 둘째 체크메이트 테스트 오류 조치, 셋째 향후 테스트 자동화 일정입니다."),
        ("B", "먼저 상품설명서 검증부터 말씀드리겠습니다. 전체 열두 개 상품 중에서 아홉 개 상품은 검증을 완료했습니다. 나머지 세 개 상품은 약관이 변경되어서 고객사에서 최종본을 받아야 진행할 수 있습니다."),
        ("A", "그러면 약관 최종본은 누가 요청하실 건가요?"),
        ("B", "제가 내일까지 고객사 담당자에게 메일로 요청하겠습니다."),
        ("A", "네, 박정우 책임님이 내일까지 약관 최종본을 요청해 주세요.", "act_terms"),
        ("C", "다음은 체크메이트 오류 조치입니다. 지난주에 발견된 오류 스물세 건 중 대부분이 날짜 형식 변환 문제였고, 수정 패치는 어제 적용했습니다."),
        ("A", "재검증은 어떻게 할까요?"),
        ("C", "제가 이번 주 금요일까지 스물세 건 전체를 재검증하고 결과를 공유드리겠습니다.", "act_recheck"),
        ("A", "좋습니다. 이지은 대리님이 금요일까지 재검증해 주시는 걸로 하겠습니다."),
        ("B", "그런데 오류 중 두 건은 원인이 아직 불명확합니다. 로그를 더 봐야 할 것 같습니다."),
        ("A", "그 두 건은 원인 분석이 필요하네요. 누가 볼지는 다음 회의에서 정하죠.", "open_cause"),
        ("A", "마지막으로 자동화 일정입니다. 저는 십이월 둘째 주까지 전 상품에 자동화를 적용하는 것을 제안합니다."),
        ("B", "약관 변경 상품 세 개만 해결되면 가능할 것 같습니다."),
        ("C", "저도 동의합니다."),
        ("A", "그럼 십이월 둘째 주까지 전 상품 자동화 적용으로 확정하겠습니다.", "dec_schedule"),
        ("B", "테스트 서버 증설은 어떻게 할까요? 지금 서버로는 동시 실행이 어렵습니다."),
        ("A", "서버 증설은 예산 확인이 필요해서 오늘 결정하기는 어렵습니다. 다음 회의에서 다시 논의하겠습니다.", "open_server"),
        ("A", "그리고 테스트 결과 보고서 양식도 새로 만들어야 하는데, 담당자는 아직 정하지 않겠습니다.", "un_report"),
        ("A", "다음 회의에서는 재검증 결과와 약관 최종본 수령 여부를 확인하겠습니다. 오늘 회의는 여기까지 하겠습니다. 수고하셨습니다."),
    ],
    expect=Expect(
        decisions=[{"id": "dec_schedule", "keywords": ["12월|십이월", "둘째 주"]}],
        not_decisions=[{"id": "open_server", "keywords": ["서버 증설"]}],
        actions=[
            {"id": "act_terms", "keywords": ["약관"], "assignee": "박정우", "deadline": "내일"},
            {"id": "act_recheck", "keywords": ["재검증"], "assignee": "이지은", "deadline": "금요일"},
        ],
        unassigned=[{"id": "un_report", "keywords": ["보고서"]}],
        open_items=[{"id": "open_server", "keywords": ["서버"]}, {"id": "open_cause", "keywords": ["원인"]}],
    ),
)

# --------------------------------------------------------------------------- long

LONG_AGENDA = ["인프라 모니터링 개선", "배포 파이프라인 안정화", "외부 보안 점검", "고객 요구사항 정리", "하반기 예산", "신규 입사자 교육"]

# Planted facts per agenda (inserted in the middle of each topic's discussion).
PLANTED: dict[str, list[tuple]] = {
    "인프라 모니터링 개선": [
        ("A", "모니터링 도구는 그라파나로 통일하는 것으로 확정하겠습니다.", "dec_grafana"),
        ("A", "한도현 선임님이 다음 주 수요일까지 대시보드 초안을 만들어 주세요.", "act_dashboard"),
        ("B", "네, 다음 주 수요일까지 초안 공유드리겠습니다."),
    ],
    "배포 파이프라인 안정화": [
        ("C", "배포 실패 원인은 아직 정확히 파악되지 않았습니다."),
        ("A", "배포 실패 원인은 다음 회의에서 다시 논의하겠습니다.", "open_deploy"),
        ("A", "롤백 절차도 문서로 정리해야 하는데, 담당자는 아직 정하지 않겠습니다.", "un_rollback"),
    ],
    "외부 보안 점검": [
        ("A", "외부 보안 점검은 일월 셋째 주에 진행하는 것으로 확정하겠습니다.", "dec_security"),
        ("A", "최윤아 책임님이 이번 달 말까지 점검 업체 견적을 세 곳에서 받아 주세요.", "act_quotes"),
        ("C", "네, 이번 달 말까지 견적 받아서 공유하겠습니다."),
    ],
    "고객 요구사항 정리": [
        ("D", "고객사에서 보낸 요구사항 정의서 초안은 제가 검토하고 있습니다."),
        ("A", "박정우 책임님이 이번 주 금요일까지 요구사항 정의서 의견을 회신해 주세요.", "act_requirements"),
    ],
    "하반기 예산": [
        ("B", "서버 증설 예산으로 이천만 원 정도를 제안드립니다."),
        ("A", "예산은 재무팀 확인이 필요해서 오늘은 결정하지 않겠습니다. 다음 회의에서 확정하죠.", "open_budget"),
    ],
    "신규 입사자 교육": [
        ("A", "신규 입사자 교육은 매월 첫째 주 화요일에 진행하는 것으로 확정하겠습니다.", "dec_training"),
        ("A", "다음 회의에서는 교육 자료 준비 상태를 확인하겠습니다.", "open_training"),
    ],
}

_SUBJECTS = ["지난주 작업", "현재 진행 상황", "테스트 결과", "운영 지표", "장애 이력", "작업 일정", "검토 의견", "개선 사항", "리소스 사용량", "협업 방식"]
_OBSERVE = [
    "{s}을 보면 전반적으로 안정적인 편입니다",
    "{s}은 계획 대비 조금 늦어지고 있습니다",
    "{s} 관련해서 몇 가지 확인할 부분이 있었습니다",
    "{s}은 팀 내부에서 한 번 더 검토가 필요해 보입니다",
    "{s}을 정리해 보니 반복되는 패턴이 있었습니다",
    "{s}에 대해서는 담당 팀과 의견을 나눴습니다",
]
_DETAIL = [
    "특히 지난 회의 이후로 크게 달라진 점은 없습니다",
    "자세한 내용은 공유 문서에 정리해 두었습니다",
    "현장에서도 비슷한 의견이 나오고 있습니다",
    "이 부분은 조금 더 지켜볼 필요가 있습니다",
    "작업량에 비해 인원이 부족한 상황입니다",
    "일부 항목은 이미 반영이 끝났습니다",
    "관련 부서와 일정 조율이 필요합니다",
    "현재로서는 큰 위험 요소는 없어 보입니다",
]
_REACT = ["네, 알겠습니다.", "그 부분은 저도 동의합니다.", "좀 더 구체적으로 설명해 주시겠어요?", "좋은 의견입니다.", "그럼 그 방향으로 계속 진행하시죠.", "추가로 의견 있으신 분 계신가요?"]


def _filler(topic: str, n: int, rng: random.Random) -> list[tuple]:
    out = []
    speakers = ["B", "C", "D"]
    for i in range(n):
        if i % 4 == 3:
            out.append(("A", rng.choice(_REACT)))
            continue
        s = rng.choice(_SUBJECTS)
        sent = f"{topic} 건에서 {rng.choice(_OBSERVE).format(s=s)}. {rng.choice(_DETAIL)}."
        out.append((rng.choice(speakers), sent))
    return out


def long_scenario(filler_per_topic: int = 44, seed: int = 7) -> Scenario:
    """~45 minutes at the default size (6 topics × ~50 lines)."""
    rng = random.Random(seed)
    lines: list[tuple] = [("A", "안녕하세요. 정기 운영 회의를 시작하겠습니다. 오늘 안건은 여섯 가지입니다. " + ", ".join(LONG_AGENDA) + " 순서로 진행하겠습니다.")]
    for topic in LONG_AGENDA:
        lines.append(("A", f"다음 안건은 {topic}입니다."))
        fill = _filler(topic, filler_per_topic, rng)
        half = len(fill) // 2
        lines += fill[:half] + PLANTED[topic] + fill[half:]
    lines.append(("A", "오늘 회의는 여기까지 하겠습니다. 수고하셨습니다."))
    return Scenario(
        name="long",
        title="정기 운영 회의",
        meeting_date="2026-11-25",
        attendees=["김민수 과장", "한도현 선임", "최윤아 책임", "박정우 책임"],
        purpose="운영 현안 점검 및 하반기 계획",
        agenda=LONG_AGENDA,
        instructions=INSTRUCTIONS,
        lines=lines,
        expect=Expect(
            decisions=[
                {"id": "dec_grafana", "keywords": ["그라파나|그래파나|grafana"]},
                {"id": "dec_security", "keywords": ["보안", "1월|일월"]},
                {"id": "dec_training", "keywords": ["교육", "첫째 주"]},
            ],
            not_decisions=[{"id": "open_budget", "keywords": ["예산"]}, {"id": "open_deploy", "keywords": ["배포 실패"]}],
            actions=[
                {"id": "act_dashboard", "keywords": ["대시보드"], "assignee": "한도현", "deadline": "수요일"},
                {"id": "act_quotes", "keywords": ["견적"], "assignee": "최윤아", "deadline": "말"},
                {"id": "act_requirements", "keywords": ["요구사항"], "assignee": "박정우", "deadline": "금요일"},
            ],
            unassigned=[{"id": "un_rollback", "keywords": ["롤백"]}],
            open_items=[{"id": "open_deploy", "keywords": ["배포"]}, {"id": "open_budget", "keywords": ["예산"]}, {"id": "open_training", "keywords": ["교육 자료"]}],
        ),
    )


SCENARIOS = {"short": lambda: SHORT, "long": long_scenario}
