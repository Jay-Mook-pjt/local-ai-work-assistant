"""Email drafting, preview and user-approved sending over SMTP.

Approval model: the client first calls preview; the server returns exactly what
would be sent plus `content_hash` (recipients, subject, body, attachment choice
and the minutes' last-update time). `send` only proceeds when the request
carries `confirm=true` and the same hash — so nothing is sent that the user did
not see, and edits made after the preview force a new preview. The AI never
calls send; it is only reachable from the 발송 button.
"""

import hashlib
import json
import logging
import re
import smtplib
import ssl
import subprocess
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailHistory, Meeting
from app.schemas.meeting import MinutesOut
from app.services import document_service, meeting_service, storage

log = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class EmailError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ---- draft -------------------------------------------------------------------


def default_draft(meeting: Meeting, minutes: MinutesOut) -> tuple[str, str]:
    lines = ["안녕하세요.", "", f'{meeting.meeting_date:%Y.%m.%d} 진행된 "{meeting.title}" 회의록을 공유드립니다.', ""]
    lines += ["■ 회의 요약", minutes.meeting_summary, ""]
    if minutes.decisions:
        lines += ["■ 의사결정 사항", *[f"{i}. {d.content}" for i, d in enumerate(minutes.decisions, 1)], ""]
    if minutes.action_items:
        lines += ["■ 후속 업무", *[f"{i}. {a.task} — 담당: {a.assignee} / 기한: {a.deadline}" for i, a in enumerate(minutes.action_items, 1)], ""]
    if minutes.open_issues:
        lines += ["■ 미결 사항", *[f"- {x}" for x in minutes.open_issues], ""]
    if minutes.next_meeting_checks:
        lines += ["■ 다음 회의 확인사항", *[f"- {x}" for x in minutes.next_meeting_checks], ""]
    lines += ["자세한 내용은 첨부한 회의록을 확인해 주세요.", "", "감사합니다."]
    return f"[회의록] {meeting.title} ({meeting.meeting_date.isoformat()})", "\n".join(lines)


# ---- validation ----------------------------------------------------------------


def clean_addresses(values: list[str], label: str) -> list[str]:
    out: list[str] = []
    for raw in values:
        addr = raw.strip()
        if not addr:
            continue
        if "\r" in addr or "\n" in addr or not EMAIL_RE.match(addr):
            raise EmailError(f"{label} 주소 형식이 올바르지 않습니다: {addr[:100]}", 422)
        if addr.lower() not in (a.lower() for a in out):
            out.append(addr)
    return out


@dataclass
class Prepared:
    to: list[str]
    cc: list[str]
    subject: str
    body: str
    attach_docx: bool
    attachment_name: str | None
    content_hash: str
    minutes_updated_at: str


def prepare(db: Session, meeting: Meeting, to: list[str], cc: list[str], subject: str | None, body: str | None, attach_docx: bool) -> Prepared:
    s = get_settings()
    minutes = meeting_service.minutes_out(db, meeting.id)
    if minutes is None:
        raise EmailError("회의록이 아직 없습니다.", 409)
    to_ = clean_addresses(to, "받는 사람")
    cc_ = [a for a in clean_addresses(cc, "참조") if a.lower() not in (t.lower() for t in to_)]
    if not to_:
        raise EmailError("받는 사람을 1명 이상 입력하세요.", 422)
    if len(to_) + len(cc_) > s.email_max_recipients:
        raise EmailError(f"수신자는 최대 {s.email_max_recipients}명까지 가능합니다.", 422)
    d_subject, d_body = default_draft(meeting, minutes)
    subject = (subject if subject is not None else d_subject).strip()
    body = (body if body is not None else d_body).replace("\r\n", "\n").strip()
    if not subject or "\r" in subject or "\n" in subject:
        raise EmailError("제목은 한 줄로 입력하세요.", 422)
    if not body:
        raise EmailError("본문을 입력하세요.", 422)
    updated = minutes.updated_at.isoformat()
    digest = hashlib.sha256(
        json.dumps({"to": to_, "cc": cc_, "subject": subject, "body": body, "attach": attach_docx, "minutes": updated}, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return Prepared(to_, cc_, subject, body, attach_docx, document_service.safe_filename(meeting) if attach_docx else None, digest, updated)


# ---- SMTP ----------------------------------------------------------------------


def smtp_password() -> str:
    s = get_settings()
    if s.smtp_password:
        return s.smtp_password
    if s.smtp_keychain_service:
        try:
            r = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-s", s.smtp_keychain_service, "-a", s.smtp_username, "-w"],
                capture_output=True, text=True, timeout=10, check=True,
            )
            return r.stdout.rstrip("\n")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            raise EmailError("macOS 키체인에서 SMTP 비밀번호를 읽지 못했습니다. SMTP_KEYCHAIN_SERVICE와 SMTP_USERNAME을 확인하세요.", 503) from exc
    return ""


def config_problem() -> str | None:
    s = get_settings()
    if not s.smtp_host:
        return "SMTP가 설정되지 않았습니다. 프로젝트 루트의 .env에 SMTP_HOST, SMTP_FROM 등을 입력한 뒤 Backend를 재시작하세요."
    if not s.smtp_from or not EMAIL_RE.match(s.smtp_from):
        return "SMTP_FROM(보내는 주소)이 설정되지 않았거나 형식이 올바르지 않습니다."
    return None


def _connect() -> smtplib.SMTP:
    s = get_settings()
    ctx = ssl.create_default_context()
    try:
        if s.smtp_port == 465:
            server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds, context=ctx)
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds)
            server.ehlo()
            if s.smtp_use_tls:
                server.starttls(context=ctx)
                server.ehlo()
        if s.smtp_username:
            server.login(s.smtp_username, smtp_password())
        return server
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailError("SMTP 로그인에 실패했습니다. 사용자 이름과 비밀번호(Gmail은 앱 비밀번호)를 확인하세요.", 502) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"SMTP 서버({s.smtp_host}:{s.smtp_port})에 연결하지 못했습니다: {type(exc).__name__}", 502) from exc


def test_connection() -> None:
    problem = config_problem()
    if problem:
        raise EmailError(problem, 409)
    server = _connect()
    try:
        server.noop()
    finally:
        server.quit()


def build_message(p: Prepared, attachment: tuple[str, bytes] | None) -> EmailMessage:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = formataddr((s.smtp_from_name, s.smtp_from))
    msg["To"] = ", ".join(p.to)
    if p.cc:
        msg["Cc"] = ", ".join(p.cc)
    msg["Subject"] = p.subject
    msg["Message-ID"] = make_msgid(domain=s.smtp_from.split("@")[-1])
    msg.set_content(p.body, charset="utf-8")
    if attachment:
        name, data = attachment
        msg.add_attachment(data, maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename=name)
    return msg


def send(db: Session, meeting: Meeting, p: Prepared) -> EmailHistory:
    """Sends the previewed email and records the outcome (SENT or FAILED)."""
    problem = config_problem()
    if problem:
        raise EmailError(problem, 409)
    attachment = None
    if p.attach_docx:
        doc = document_service.export(db, meeting)  # fresh DOCX from the same minutes that were previewed
        attachment = (doc.filename, storage.resolve(doc.stored_path).read_bytes())
    msg = build_message(p, attachment)
    record = EmailHistory(meeting_id=meeting.id, to=p.to, cc=p.cc, subject=p.subject, body=p.body, attachment=attachment[0] if attachment else None, status="FAILED")
    db.add(record)
    try:
        server = _connect()
        try:
            refused = server.send_message(msg)
        finally:
            try:
                server.quit()
            except smtplib.SMTPException:
                pass
        if refused:
            record.error = "일부 수신자가 거부되었습니다: " + ", ".join(refused)
        record.status = "SENT"
        log.info("Email sent for meeting %s to %d recipient(s)", meeting.id, len(p.to) + len(p.cc))
    except EmailError as exc:
        record.error = str(exc)
        db.commit()
        raise
    except (smtplib.SMTPException, OSError) as exc:
        record.error = f"발송 실패: {type(exc).__name__}: {exc}"[:1000]
        db.commit()
        raise EmailError(record.error, 502) from exc
    db.commit()
    return record
