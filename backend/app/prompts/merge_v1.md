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
아래는 긴 회의를 구간별로 나누어 추출한 결과(JSON)이다. 이를 하나의 최종 회의록으로 통합하라.
- meeting_summary: 회의 전체를 5문장 이내로 요약한다. 결정사항과 주요 후속 업무를 중심으로 쓴다.
- discussion_items: 회의 안건 순서대로 정리한다. 같은 주제는 하나로 합치고, 가장 이른 timestamp를 쓴다.
- decisions, action_items: 중복(같은 내용이 여러 구간에 나온 경우)을 하나로 합친다. evidence와 timestamp는 입력에 있는 값을 그대로 유지한다. 새로운 항목을 만들지 않는다.
- 한 구간에서 미결이었던 사항이 다른 구간에서 결정되었다면 decisions에만 두고 open_issues에서 뺀다.
- open_issues, next_meeting_checks: 중복을 제거해 정리한다.
- 입력에 없는 내용을 추가하지 않는다. 담당자·기한이 입력에서 "미확인"이면 그대로 "미확인"으로 둔다.

# 구간별 추출 결과
$chunks
