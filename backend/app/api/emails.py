from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import DB, MeetingDep
from app.config import get_settings
from app.schemas.meeting import EmailHistoryOut
from app.services import email_service, meeting_service

router = APIRouter(prefix="/api", tags=["email"])


class EmailDraftOut(BaseModel):
    subject: str
    body: str
    smtp_ready: bool
    smtp_problem: str | None
    sender: str | None


class EmailRequest(BaseModel):
    to: list[str] = Field(default_factory=list, max_length=100)
    cc: list[str] = Field(default_factory=list, max_length=100)
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=50000)
    attach_docx: bool = True


class EmailPreviewOut(BaseModel):
    to: list[str]
    cc: list[str]
    sender: str | None
    subject: str
    body: str
    attachment_name: str | None
    content_hash: str
    smtp_ready: bool
    smtp_problem: str | None


class EmailSendRequest(EmailRequest):
    content_hash: str = Field(min_length=64, max_length=64)
    confirm: bool = False


def _sender() -> str | None:
    s = get_settings()
    return f"{s.smtp_from_name} <{s.smtp_from}>" if s.smtp_from else None


def _raise(exc: email_service.EmailError) -> None:
    raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/meetings/{id}/email/draft", response_model=EmailDraftOut)
def draft(meeting: MeetingDep, db: DB) -> EmailDraftOut:
    minutes = meeting_service.minutes_out(db, meeting.id)
    if minutes is None:
        raise HTTPException(409, "회의록이 아직 없습니다.")
    subject, body = email_service.default_draft(meeting, minutes)
    problem = email_service.config_problem()
    return EmailDraftOut(subject=subject, body=body, smtp_ready=problem is None, smtp_problem=problem, sender=_sender())


@router.post("/meetings/{id}/email/preview", response_model=EmailPreviewOut)
def preview(meeting: MeetingDep, body: EmailRequest, db: DB) -> EmailPreviewOut:
    """Shows exactly what would be sent. Nothing is sent and no file is written."""
    try:
        p = email_service.prepare(db, meeting, body.to, body.cc, body.subject, body.body, body.attach_docx)
    except email_service.EmailError as exc:
        _raise(exc)
    problem = email_service.config_problem()
    return EmailPreviewOut(
        to=p.to, cc=p.cc, sender=_sender(), subject=p.subject, body=p.body, attachment_name=p.attachment_name,
        content_hash=p.content_hash, smtp_ready=problem is None, smtp_problem=problem,
    )


@router.post("/meetings/{id}/email/send", response_model=EmailHistoryOut)
def send(meeting: MeetingDep, body: EmailSendRequest, db: DB) -> EmailHistoryOut:
    """Sends only with explicit confirmation of an unchanged preview (see email_service)."""
    if not body.confirm:
        raise HTTPException(400, "발송 확인이 필요합니다.")
    try:
        p = email_service.prepare(db, meeting, body.to, body.cc, body.subject, body.body, body.attach_docx)
        if p.content_hash != body.content_hash:
            raise email_service.EmailError("미리보기 이후 메일 내용이나 회의록이 바뀌었습니다. 다시 미리보기를 확인한 뒤 발송하세요.", 409)
        return EmailHistoryOut.model_validate(email_service.send(db, meeting, p))
    except email_service.EmailError as exc:
        _raise(exc)
        raise  # unreachable; keeps type checkers happy


@router.post("/email/test-connection")
def test_connection() -> dict[str, str]:
    """Logs in to the SMTP server without sending anything."""
    try:
        email_service.test_connection()
    except email_service.EmailError as exc:
        _raise(exc)
    return {"status": "ok", "message": f"SMTP 서버 {get_settings().smtp_host}에 로그인했습니다."}
