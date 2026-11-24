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
아래는 회의 전사문의 $part 구간이다($part_index/$part_total). 이 구간에서 다음을 추출하라.
- discussion_items: 논의된 주제별 핵심 내용. topic은 가능하면 위 회의 안건 이름을 그대로 쓰고, 안건이 없으면 대화 흐름에 따라 주제를 나눈다. 건수·소요 시간·빈도·금액 같은 수치는 빠뜨리지 않고 그대로 적는다. timestamp는 해당 논의가 시작된 [시:분:초].
- decisions: 확정된 의사결정 (근거 문장·타임스탬프 포함)
- action_items: 후속 업무 (task, assignee, deadline, 근거 문장·타임스탬프 포함)
- open_issues: 결론이 나지 않았거나 추가 확인이 필요한 사항
- next_meeting_checks: 다음 회의에서 확인하기로 한 사항

해당 항목이 없으면 빈 배열로 둔다. 구간 시작 부분에 "(이전 구간에서 이어짐)"으로 표시된 줄은 앞 구간의 문맥이므로 그 줄만으로 새 항목을 만들지 않는다.

# 전사문
$transcript
