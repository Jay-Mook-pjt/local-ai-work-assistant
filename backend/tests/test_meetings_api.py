from app.config import get_settings
from app.models import Transcript
from tests.conftest import make_meeting, upload


def test_create_and_get_meeting(client):
    m = make_meeting(client, title="  공백 제거  ", attendees=[" 김민수 ", "", "이지은"])
    assert m["title"] == "공백 제거"
    assert m["attendees"] == ["김민수", "이지은"]
    assert m["status"] == "PENDING" and m["audio"] is None and len(m["id"]) == 32
    assert client.get(f"/api/meetings/{m['id']}").json()["title"] == "공백 제거"


def test_create_validation(client):
    assert client.post("/api/meetings", json={"title": "   ", "meeting_date": "2026-11-20"}).status_code == 422
    assert client.post("/api/meetings", json={"title": "x", "meeting_date": "not-a-date"}).status_code == 422
    assert client.post("/api/meetings", json={"title": "x" * 201, "meeting_date": "2026-11-20"}).status_code == 422


def test_get_unknown_and_malformed_ids(client):
    assert client.get("/api/meetings/" + "0" * 32).status_code == 404
    assert client.get("/api/meetings/..%2F..%2Fetc").status_code in (404, 422)
    assert client.get("/api/meetings/abc").status_code == 422


def test_list_filters(client, db):
    a = make_meeting(client, title="방카슈랑스 테스트", meeting_date="2026-11-20")
    b = make_meeting(client, title="주간 회의", meeting_date="2026-10-01", attendees=["최윤아"])
    db.add(Transcript(meeting_id=b["id"], language="ko", model="t", segments=[], full_text="배포 파이프라인 실패 원인"))
    db.commit()

    ids = lambda r: [m["id"] for m in r.json()]  # noqa: E731
    assert ids(client.get("/api/meetings")) == [a["id"], b["id"]]  # newest meeting date first
    assert ids(client.get("/api/meetings", params={"q": "방카"})) == [a["id"]]
    assert ids(client.get("/api/meetings", params={"q": "최윤아"})) == [b["id"]]  # attendees
    assert ids(client.get("/api/meetings", params={"q": "파이프라인"})) == [b["id"]]  # transcript content
    assert ids(client.get("/api/meetings", params={"from": "2026-11-01"})) == [a["id"]]
    assert ids(client.get("/api/meetings", params={"to": "2026-10-31"})) == [b["id"]]
    assert ids(client.get("/api/meetings", params={"status": "UPLOADED"})) == []


def test_search_treats_sql_wildcards_and_quotes_literally(client):
    make_meeting(client, title="일반 회의")
    assert client.get("/api/meetings", params={"q": "%"}).json() == []
    assert client.get("/api/meetings", params={"q": "_"}).json() == []
    assert client.get("/api/meetings", params={"q": "' OR 1=1 --"}).json() == []


def test_delete_removes_rows_and_files(client, media_dir):
    m = make_meeting(client)
    assert upload(client, m["id"], media_dir / "tone.wav").status_code == 201
    original = get_settings().storage_dir / "audio/original" / m["id"]
    assert any(original.iterdir())

    assert client.delete(f"/api/meetings/{m['id']}").status_code == 204
    assert not original.exists()
    assert client.get(f"/api/meetings/{m['id']}").status_code == 404
    assert client.delete(f"/api/meetings/{m['id']}").status_code == 404


def test_transcript_and_minutes_empty_by_default(client):
    m = make_meeting(client)
    assert client.get(f"/api/meetings/{m['id']}/transcript").json() is None
    assert client.get(f"/api/meetings/{m['id']}/minutes").json() is None
    assert client.get(f"/api/meetings/{m['id']}/documents").json() == []
    assert client.get(f"/api/meetings/{m['id']}/emails").json() == []
