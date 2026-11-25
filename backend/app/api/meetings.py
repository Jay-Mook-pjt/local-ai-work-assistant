"""Meeting CRUD, transcript, minutes, action items, documents, email history, dashboard."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.deps import DB, MeetingDep
from app.models import EmailHistory, Transcript
from app.schemas.meeting import (
    ActionItemOut,
    ActionItemStatusUpdate,
    ActionItemWithMeeting,
    DashboardOut,
    DocumentOut,
    EmailHistoryOut,
    JobStatus,
    MeetingCreate,
    MeetingOut,
    MinutesOut,
    MinutesUpdate,
    SpeakerNamesUpdate,
    TranscriptOut,
)
from app.services import meeting_service

router = APIRouter(prefix="/api", tags=["meetings"])


@router.post("/meetings", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
def create_meeting(body: MeetingCreate, db: DB) -> MeetingOut:
    return MeetingOut.model_validate(meeting_service.create_meeting(db, body))


@router.get("/meetings", response_model=list[MeetingOut])
def list_meetings(
    db: DB,
    q: Annotated[str | None, Query(max_length=200)] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    status_: Annotated[JobStatus | None, Query(alias="status")] = None,
) -> list[MeetingOut]:
    return [MeetingOut.model_validate(m) for m in meeting_service.list_meetings(db, q, date_from, date_to, status_)]


@router.get("/meetings/{id}", response_model=MeetingOut)
def get_meeting(meeting: MeetingDep) -> MeetingOut:
    return MeetingOut.model_validate(meeting)


@router.delete("/meetings/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(meeting: MeetingDep, db: DB) -> Response:
    """Deletes the meeting, its DB rows and every stored file (audio, transcript, documents)."""
    try:
        meeting_service.delete_meeting(db, meeting.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/meetings/{id}/transcript", response_model=TranscriptOut | None)
def get_transcript(meeting: MeetingDep, db: DB) -> TranscriptOut | None:
    t = db.scalar(select(Transcript).where(Transcript.meeting_id == meeting.id))
    return TranscriptOut.model_validate(t) if t else None


@router.put("/meetings/{id}/speakers", response_model=MeetingOut)
def set_speakers(meeting: MeetingDep, body: SpeakerNamesUpdate, db: DB) -> MeetingOut:
    """Names diarized speakers ('화자 1' → '김민수 과장'); also updates the current minutes."""
    try:
        return MeetingOut.model_validate(meeting_service.set_speaker_names(db, meeting, body.names))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/meetings/{id}/minutes", response_model=MinutesOut | None)
def get_minutes(meeting: MeetingDep, db: DB) -> MinutesOut | None:
    return meeting_service.minutes_out(db, meeting.id)


@router.put("/meetings/{id}/minutes", response_model=MinutesOut)
def update_minutes(meeting: MeetingDep, body: MinutesUpdate, db: DB) -> MinutesOut:
    return meeting_service.save_minutes(db, meeting.id, body, edited=True)


@router.patch("/meetings/{id}/action-items/{item_id}", response_model=ActionItemOut)
def update_action_item(meeting: MeetingDep, item_id: str, body: ActionItemStatusUpdate, db: DB) -> ActionItemOut:
    try:
        return ActionItemOut.model_validate(meeting_service.update_action_status(db, meeting.id, item_id, body.status))
    except meeting_service.NotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/meetings/{id}/documents", response_model=list[DocumentOut])
def list_meeting_documents(meeting: MeetingDep) -> list[DocumentOut]:
    return [DocumentOut.model_validate(d) for d in meeting.documents]


@router.get("/meetings/{id}/emails", response_model=list[EmailHistoryOut])
def list_meeting_emails(meeting: MeetingDep) -> list[EmailHistoryOut]:
    return [EmailHistoryOut.model_validate(e) for e in meeting.emails]


@router.get("/action-items", response_model=list[ActionItemWithMeeting])
def list_action_items(
    db: DB,
    status_: Annotated[Literal["OPEN", "PENDING", "IN_PROGRESS", "DONE"] | None, Query(alias="status")] = None,
    assignee: Annotated[str | None, Query(max_length=200)] = None,
) -> list[ActionItemWithMeeting]:
    return meeting_service.list_action_items(db, status_, assignee)


@router.get("/emails", response_model=list[EmailHistoryOut])
def list_emails(db: DB) -> list[EmailHistoryOut]:
    return [EmailHistoryOut.model_validate(e) for e in db.scalars(select(EmailHistory).order_by(EmailHistory.sent_at.desc()).limit(500))]


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: DB) -> DashboardOut:
    return meeting_service.dashboard(db)
