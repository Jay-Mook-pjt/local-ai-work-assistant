from tests.conftest import make_meeting

MINUTES = {
    "meeting_summary": "요약",
    "discussion_items": [{"topic": "검증", "content": "9개 완료", "speaker": "미확인", "timestamp": "00:00:12"}],
    "decisions": [{"content": "12월 둘째 주 적용", "evidence": "확정으로 하겠습니다", "timestamp": "00:30:20"}],
    "action_items": [
        {"task": "오류 재검증", "assignee": "이지은", "deadline": "금요일", "status": "IN_PROGRESS"},
        {"task": "최종본 요청", "assignee": "  ", "deadline": ""},
    ],
    "open_issues": ["서버 증설", "  "],
    "next_meeting_checks": ["재검증 결과"],
}


def put(client, mid, body):
    return client.put(f"/api/meetings/{mid}/minutes", json=body)


def test_save_and_read_minutes(client):
    m = make_meeting(client)
    r = put(client, m["id"], MINUTES)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["edited"] is True
    assert out["open_issues"] == ["서버 증설"]
    a1, a2 = out["action_items"]
    assert (a1["task"], a1["status"]) == ("오류 재검증", "IN_PROGRESS")
    assert (a2["assignee"], a2["deadline"], a2["timestamp"]) == ("미확인", "미확인", "미확인")  # blanks become 미확인
    assert client.get(f"/api/meetings/{m['id']}/minutes").json() == out


def test_update_keeps_existing_action_ids_and_removes_missing(client):
    m = make_meeting(client)
    first = put(client, m["id"], MINUTES).json()["action_items"]
    body = MINUTES | {"action_items": [first[1] | {"task": "최종본 요청(수정)"}, {"id": "client-temp-id", "task": "새 업무"}]}
    second = put(client, m["id"], body).json()["action_items"]
    assert second[0]["id"] == first[1]["id"] and second[0]["task"] == "최종본 요청(수정)"
    assert second[1]["id"] not in (first[0]["id"], first[1]["id"], "client-temp-id")
    assert len(second) == 2


def test_minutes_validation(client):
    m = make_meeting(client)
    assert put(client, m["id"], MINUTES | {"meeting_summary": ""}).status_code == 422
    assert put(client, m["id"], MINUTES | {"action_items": [{"task": "x", "status": "WHATEVER"}]}).status_code == 422
    assert put(client, "f" * 32, MINUTES).status_code == 404


def test_action_items_listing_and_status_update(client):
    a = make_meeting(client, title="A", meeting_date="2026-11-20")
    b = make_meeting(client, title="B", meeting_date="2026-11-01")
    items_a = put(client, a["id"], MINUTES).json()["action_items"]
    put(client, b["id"], MINUTES | {"action_items": [{"task": "B 업무", "assignee": "최윤아"}]})

    all_items = client.get("/api/action-items").json()
    assert [i["task"] for i in all_items][0] == "오류 재검증"  # IN_PROGRESS first
    assert {i["meeting_title"] for i in all_items} == {"A", "B"}

    r = client.patch(f"/api/meetings/{a['id']}/action-items/{items_a[0]['id']}", json={"status": "DONE"})
    assert r.status_code == 200 and r.json()["status"] == "DONE"
    open_items = client.get("/api/action-items", params={"status": "OPEN"}).json()
    assert items_a[0]["id"] not in [i["id"] for i in open_items]
    assert [i["task"] for i in client.get("/api/action-items", params={"assignee": "최윤아"}).json()] == ["B 업무"]

    # An item cannot be updated through another meeting's URL.
    assert client.patch(f"/api/meetings/{b['id']}/action-items/{items_a[1]['id']}", json={"status": "DONE"}).status_code == 404
    assert client.patch(f"/api/meetings/{a['id']}/action-items/{items_a[1]['id']}", json={"status": "NOPE"}).status_code == 422


def test_dashboard(client):
    m = make_meeting(client, meeting_date="2000-01-01")
    put(client, m["id"], MINUTES)
    d = client.get("/api/dashboard").json()
    assert d["total_meetings"] == 1
    assert d["meetings_this_month"] == 0
    assert d["processing"] == 0
    assert d["open_action_items"] == 2
    assert [x["id"] for x in d["recent_meetings"]] == [m["id"]]
    assert len(d["recent_action_items"]) == 2
    assert d["active_jobs"] == [] and d["recent_documents"] == []


def test_search_finds_minutes_content(client):
    m = make_meeting(client, title="제목")
    put(client, m["id"], MINUTES | {"meeting_summary": "테스트 서버 증설 논의"})
    assert [x["id"] for x in client.get("/api/meetings", params={"q": "증설 논의"}).json()] == [m["id"]]
    assert [x["id"] for x in client.get("/api/meetings", params={"q": "오류 재검증"}).json()] == [m["id"]]
