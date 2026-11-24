# 회의 정보
- 회의 제목: $title
- 회의 날짜: $meeting_date
- 참석자: $attendees
- 회의 목적: $purpose
- 회의 안건:
$agenda

# 사용자 추가 지시사항
$instructions

# 작업
아래 회의 전사문 전체를 읽고 최종 회의록을 작성하라.
- meeting_summary: 회의 전체를 5문장 이내로 요약한다. 결정사항과 주요 후속 업무를 중심으로 쓴다.
- discussion_items: 회의 안건 순서대로 주제별 핵심 내용을 정리한다. topic은 가능하면 위 회의 안건 이름을 그대로 쓴다. 안건이 입력되지 않았으면 대화 흐름에 따라 주제를 3~6개로 나눈다. 건수·소요 시간·빈도·금액 같은 수치는 빠뜨리지 않고 그대로 적는다. timestamp는 해당 논의가 시작된 [시:분:초].
- decisions: 확정된 의사결정 (근거 문장·타임스탬프 포함)
- action_items: 후속 업무 (task, assignee, deadline, 근거 문장·타임스탬프 포함)
- open_issues: 결론이 나지 않았거나 추가 확인이 필요한 사항
- next_meeting_checks: 다음 회의에서 확인하기로 한 사항

해당 항목이 없으면 빈 배열로 둔다.

# 전사문
$transcript
