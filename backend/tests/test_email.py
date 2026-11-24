import email
import socket
import subprocess
from email import policy

import pytest
from aiosmtpd.controller import Controller

from app.config import get_settings
from app.services import email_service
from tests.conftest import make_meeting
from tests.test_minutes import MINUTES


class Inbox:
    def __init__(self):
        self.messages: list[tuple[list[str], email.message.EmailMessage]] = []

    async def handle_DATA(self, server, session, envelope):  # noqa: N802 - aiosmtpd hook name
        self.messages.append((envelope.rcpt_tos, email.message_from_bytes(envelope.content, policy=policy.default)))
        return "250 OK"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def smtp(monkeypatch):
    """Real SMTP server on localhost (no TLS, no auth) + settings pointing at it."""
    inbox = Inbox()
    port = _free_port()
    ctl = Controller(inbox, hostname="127.0.0.1", port=port)
    ctl.start()
    s = get_settings()
    for k, v in {"smtp_host": "127.0.0.1", "smtp_port": port, "smtp_use_tls": False, "smtp_username": "", "smtp_password": "", "smtp_from": "assistant@example.com", "smtp_from_name": "AI 회의록 비서"}.items():
        monkeypatch.setattr(s, k, v)
    yield inbox
    ctl.stop()


@pytest.fixture
def meeting(client):
    m = make_meeting(client, title="방카 테스트 회의")
    client.put(f"/api/meetings/{m['id']}/minutes", json=MINUTES)
    return m


def preview(client, mid, **kw):
    body = {"to": ["team@example.com"], "cc": [], "attach_docx": True} | kw
    return client.post(f"/api/meetings/{mid}/email/preview", json=body)


def send(client, mid, pv: dict, **kw):
    body = {"to": pv["to"], "cc": pv["cc"], "subject": pv["subject"], "body": pv["body"], "attach_docx": pv["attachment_name"] is not None, "content_hash": pv["content_hash"], "confirm": True} | kw
    return client.post(f"/api/meetings/{mid}/email/send", json=body)


def test_draft_is_generated_from_minutes(client, meeting, smtp):
    d = client.get(f"/api/meetings/{meeting['id']}/email/draft").json()
    assert d["subject"] == "[회의록] 방카 테스트 회의 (2026-11-20)"
    assert "■ 의사결정 사항" in d["body"] and "오류 재검증 — 담당: 이지은 / 기한: 금요일" in d["body"]
    assert d["smtp_ready"] is True and d["sender"] == "AI 회의록 비서 <assistant@example.com>"


def test_preview_validates_and_has_no_side_effects(client, meeting, smtp):
    mid = meeting["id"]
    assert preview(client, mid, to=[]).status_code == 422
    assert preview(client, mid, to=["not-an-email"]).status_code == 422
    assert preview(client, mid, to=["a@b.com\nBcc: evil@x.com"]).status_code == 422  # header injection
    assert preview(client, mid, subject="제목\r\nBcc: evil@x.com").status_code == 422
    assert preview(client, mid, to=[f"u{i}@x.com" for i in range(51)]).status_code == 422

    pv = preview(client, mid, to=["Team@example.com", "team@example.com", " "], cc=["team@example.com", "lead@example.com"]).json()
    assert pv["to"] == ["Team@example.com"] and pv["cc"] == ["lead@example.com"]  # de-duplicated
    assert pv["attachment_name"] == "20261120_방카_테스트_회의_회의록.docx"
    assert len(pv["content_hash"]) == 64
    assert client.get(f"/api/meetings/{mid}/documents").json() == []  # preview wrote nothing
    assert smtp.messages == [] and client.get(f"/api/meetings/{mid}/emails").json() == []


def test_send_requires_confirmation_and_matching_preview(client, meeting, smtp):
    mid = meeting["id"]
    pv = preview(client, mid).json()
    assert send(client, mid, pv, confirm=False).status_code == 400
    assert send(client, mid, pv, subject="바뀐 제목").status_code == 409  # differs from what was previewed
    assert send(client, mid, pv, content_hash="0" * 64).status_code == 409
    assert smtp.messages == []


def test_minutes_edited_after_preview_blocks_send(client, meeting, smtp):
    mid = meeting["id"]
    pv = preview(client, mid).json()
    client.put(f"/api/meetings/{mid}/minutes", json=MINUTES | {"meeting_summary": "수정된 요약"})
    r = send(client, mid, pv)
    assert r.status_code == 409 and "다시 미리보기" in r.json()["detail"]
    assert smtp.messages == []


def test_send_delivers_korean_mail_with_docx_and_records_history(client, meeting, smtp):
    mid = meeting["id"]
    pv = preview(client, mid, cc=["lead@example.com"], body="안녕하세요.\n회의록을 공유드립니다.").json()
    r = send(client, mid, pv)
    assert r.status_code == 200, r.text
    hist = r.json()
    assert hist["status"] == "SENT" and hist["attachment"] == pv["attachment_name"]

    (rcpts, msg), = smtp.messages
    assert sorted(rcpts) == ["lead@example.com", "team@example.com"]
    assert msg["Subject"] == "[회의록] 방카 테스트 회의 (2026-11-20)"
    assert msg["From"] == "AI 회의록 비서 <assistant@example.com>"
    assert msg["Cc"] == "lead@example.com" and "Bcc" not in msg
    assert msg.get_body(("plain",)).get_content().replace("\r\n", "\n").strip() == "안녕하세요.\n회의록을 공유드립니다."  # SMTP uses CRLF on the wire
    (att,) = list(msg.iter_attachments())
    assert att.get_filename() == pv["attachment_name"]
    assert att.get_content()[:2] == b"PK"  # a real .docx (zip)

    assert client.get(f"/api/meetings/{mid}/emails").json()[0]["id"] == hist["id"]
    assert client.get("/api/emails").json()[0]["status"] == "SENT"
    assert len(client.get(f"/api/meetings/{mid}/documents").json()) == 1  # the attached file is kept


def test_send_without_attachment(client, meeting, smtp):
    pv = preview(client, meeting["id"], attach_docx=False).json()
    assert pv["attachment_name"] is None
    assert send(client, meeting["id"], pv).status_code == 200
    assert list(smtp.messages[0][1].iter_attachments()) == []


def test_smtp_failure_is_recorded(client, meeting, smtp, monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_port", _free_port())  # nothing listening
    pv = preview(client, meeting["id"]).json()
    r = send(client, meeting["id"], pv)
    assert r.status_code == 502 and "연결하지 못했습니다" in r.json()["detail"]
    hist = client.get(f"/api/meetings/{meeting['id']}/emails").json()
    assert hist[0]["status"] == "FAILED" and hist[0]["error"]


def test_not_configured(client, meeting, monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    d = client.get(f"/api/meetings/{meeting['id']}/email/draft").json()
    assert d["smtp_ready"] is False and "SMTP_HOST" in d["smtp_problem"]
    pv = preview(client, meeting["id"]).json()  # preview still works
    r = send(client, meeting["id"], pv)
    assert r.status_code == 409 and "SMTP" in r.json()["detail"]


def test_connection_check(client, smtp):
    r = client.post("/api/email/test-connection")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert smtp.messages == []


def test_keychain_password(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "smtp_password", "")
    monkeypatch.setattr(s, "smtp_keychain_service", "lawa-smtp")
    monkeypatch.setattr(s, "smtp_username", "me@example.com")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="s3cret\n", stderr="")

    monkeypatch.setattr(email_service.subprocess, "run", fake_run)
    assert email_service.smtp_password() == "s3cret"
    assert calls[0] == ["/usr/bin/security", "find-generic-password", "-s", "lawa-smtp", "-a", "me@example.com", "-w"]
