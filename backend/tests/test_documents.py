from io import BytesIO
from urllib.parse import unquote

from docx import Document as Docx

from app.config import get_settings
from app.services.document_service import safe_filename
from tests.conftest import make_meeting
from tests.test_minutes import MINUTES


def _with_minutes(client, **kw):
    m = make_meeting(client, **kw)
    assert client.put(f"/api/meetings/{m['id']}/minutes", json=MINUTES).status_code == 200
    return m


def _text(docx_bytes: bytes) -> str:
    d = Docx(BytesIO(docx_bytes))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)


def test_export_requires_minutes(client):
    m = make_meeting(client)
    r = client.post(f"/api/meetings/{m['id']}/export")
    assert r.status_code == 409 and "회의록" in r.json()["detail"]


def test_export_download_and_content(client):
    m = _with_minutes(client, title="방카슈랑스/테스트: 회의", attendees=["김민수 과장", "이지은 대리"], purpose="진행 점검")
    r = client.post(f"/api/meetings/{m['id']}/export")
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["filename"] == "20261120_방카슈랑스_테스트_회의_회의록.docx"
    assert client.get(f"/api/meetings/{m['id']}/documents").json()[0]["id"] == doc["id"]

    dl = client.get(f"/api/documents/{doc['id']}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert unquote(dl.headers["content-disposition"].split("filename*=UTF-8''")[1]) == doc["filename"]

    text = _text(dl.content)
    for heading in ["1. 회의 개요", "2. 회의 목적", "3. 참석자", "4. 주요 논의사항", "5. 의사결정 사항", "6. 담당자별 후속 업무", "7. 미결 사항", "8. 다음 회의 확인사항"]:
        assert heading in text
    assert "김민수 과장, 이지은 대리" in text and "진행 점검" in text
    assert "12월 둘째 주 적용" in text and "확정으로 하겠습니다" in text  # decision + evidence
    assert "1 | 오류 재검증 | 이지은 | 금요일 | 진행 중" in text
    assert "2 | 최종본 요청 | 미확인 | 미확인 | 대기" in text
    assert "서버 증설" in text and "재검증 결과" in text

    # 미확인 is rendered in orange so it stands out from real data.
    d = Docx(BytesIO(dl.content))
    runs = [r for t in d.tables for row in t.rows for c in row.cells for p in c.paragraphs for r in p.runs if r.text == "미확인"]
    assert runs and all(str(r.font.color.rgb) == "B45309" for r in runs)


def test_delete_document_and_meeting_cleanup(client):
    m = _with_minutes(client)
    doc = client.post(f"/api/meetings/{m['id']}/export").json()
    exports = get_settings().storage_dir / "exports" / m["id"]
    assert len(list(exports.iterdir())) == 1
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert list(exports.iterdir()) == []
    assert client.get(f"/api/documents/{doc['id']}/download").status_code == 404

    client.post(f"/api/meetings/{m['id']}/export")
    client.delete(f"/api/meetings/{m['id']}")
    assert not exports.exists()


def test_download_missing_file_is_410(client):
    m = _with_minutes(client)
    doc = client.post(f"/api/meetings/{m['id']}/export").json()
    for f in (get_settings().storage_dir / "exports" / m["id"]).iterdir():
        f.unlink()
    assert client.get(f"/api/documents/{doc['id']}/download").status_code == 410


def test_safe_filename_strips_reserved_characters():
    from datetime import date

    from app.models import Meeting

    m = Meeting(title='../../a\\b:c*?"<>|  회의', meeting_date=date(2026, 1, 2))
    name = safe_filename(m)
    assert name.startswith("20260102_") and name.endswith("_회의록.docx")
    assert not any(ch in name for ch in '/\\:*?"<>|')


def test_dashboard_lists_recent_documents(client):
    m = _with_minutes(client)
    doc = client.post(f"/api/meetings/{m['id']}/export").json()
    d = client.get("/api/dashboard").json()
    assert d["recent_documents"][0]["id"] == doc["id"] and d["recent_documents"][0]["meeting_title"] == m["title"]
