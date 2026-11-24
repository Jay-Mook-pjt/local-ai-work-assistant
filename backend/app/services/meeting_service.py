"""Meeting queries and mutations used by the API routers."""

import logging
from datetime import UTC, date, datetime

from sqlalchemy import String, case, cast, func, or_, select, union
from sqlalchemy.orm import Session, selectinload

from app.models import ActionItem, Document, Job, Meeting, MeetingMinutes, Transcript
from app.schemas.meeting import (
    ACTIVE_JOB_STATUSES,
    ActionItemOut,
    ActionItemWithMeeting,
    ActiveJobOut,
    DashboardOut,
    MeetingCreate,
    MeetingOut,
    MinutesOut,
    MinutesUpdate,
    RecentDocumentOut,
)
from app.services import storage

log = logging.getLogger(__name__)


class NotFoundError(Exception):
    pass


def _like(q: str) -> str:
    """LIKE pattern with user wildcards escaped (values are always bound parameters)."""
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def get_meeting(db: Session, meeting_id: str) -> Meeting:
    m = db.get(Meeting, meeting_id, options=[selectinload(Meeting.audio)])
    if m is None:
        raise NotFoundError("회의를 찾을 수 없습니다.")
    return m


def create_meeting(db: Session, data: MeetingCreate) -> Meeting:
    m = Meeting(**data.model_dump(), status="PENDING")
    db.add(m)
    db.commit()
    db.refresh(m)
    log.info("Created meeting %s", m.id)
    return m


def list_meetings(
    db: Session, q: str | None = None, date_from: date | None = None, date_to: date | None = None, status: str | None = None, limit: int = 200
) -> list[Meeting]:
    stmt = select(Meeting).options(selectinload(Meeting.audio))
    if status:
        stmt = stmt.where(Meeting.status == status)
    if date_from:
        stmt = stmt.where(Meeting.meeting_date >= date_from)
    if date_to:
        stmt = stmt.where(Meeting.meeting_date <= date_to)
    if q and q.strip():
        pat = _like(q.strip())
        content_hits = union(
            select(Transcript.meeting_id).where(Transcript.full_text.ilike(pat, escape="\\")),
            select(MeetingMinutes.meeting_id).where(MeetingMinutes.meeting_summary.ilike(pat, escape="\\")),
            select(MeetingMinutes.meeting_id).where(cast(MeetingMinutes.discussion_items, String).ilike(pat, escape="\\")),
            select(ActionItem.meeting_id).where(ActionItem.task.ilike(pat, escape="\\")),
        )
        stmt = stmt.where(
            or_(
                Meeting.title.ilike(pat, escape="\\"),
                Meeting.purpose.ilike(pat, escape="\\"),
                cast(Meeting.attendees, String).ilike(pat, escape="\\"),
                cast(Meeting.agenda, String).ilike(pat, escape="\\"),
                Meeting.id.in_(content_hits),
            )
        )
    stmt = stmt.order_by(Meeting.meeting_date.desc(), Meeting.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def delete_meeting(db: Session, meeting_id: str) -> None:
    m = get_meeting(db, meeting_id)
    if db.scalar(select(Job.id).where(Job.meeting_id == m.id, Job.status.in_([s for s in ACTIVE_JOB_STATUSES if s != "PENDING"]))):
        raise ValueError("처리 중인 회의는 삭제할 수 없습니다. 처리가 끝난 뒤 다시 시도하세요.")
    db.delete(m)
    db.commit()
    storage.delete_meeting_files(meeting_id)
    log.info("Deleted meeting %s", meeting_id)


def minutes_out(db: Session, meeting_id: str) -> MinutesOut | None:
    mn = db.scalar(select(MeetingMinutes).where(MeetingMinutes.meeting_id == meeting_id))
    if mn is None:
        return None
    items = db.scalars(select(ActionItem).where(ActionItem.meeting_id == meeting_id).order_by(ActionItem.position)).all()
    return MinutesOut(
        meeting_id=meeting_id,
        meeting_summary=mn.meeting_summary,
        discussion_items=mn.discussion_items,
        decisions=mn.decisions,
        action_items=[ActionItemOut.model_validate(a) for a in items],
        open_issues=mn.open_issues,
        next_meeting_checks=mn.next_meeting_checks,
        llm_model=mn.llm_model,
        review_notes=mn.review_notes or [],
        edited=mn.edited,
        updated_at=mn.updated_at,
    )


def save_minutes(
    db: Session, meeting_id: str, data: MinutesUpdate, *, llm_model: str | None = None, edited: bool = True, review_notes: list[str] | None = None
) -> MinutesOut:
    """Replace the minutes and action items. Existing action item ids are kept."""
    get_meeting(db, meeting_id)
    mn = db.scalar(select(MeetingMinutes).where(MeetingMinutes.meeting_id == meeting_id))
    if mn is None:
        mn = MeetingMinutes(meeting_id=meeting_id, llm_model=llm_model or "")
        db.add(mn)
    mn.meeting_summary = data.meeting_summary.strip()
    mn.discussion_items = [d.model_dump() for d in data.discussion_items]
    mn.decisions = [d.model_dump() for d in data.decisions]
    mn.open_issues = data.open_issues
    mn.next_meeting_checks = data.next_meeting_checks
    mn.edited = edited
    if llm_model is not None:
        mn.llm_model = llm_model
    if review_notes is not None:  # set by AI analysis; user edits keep the existing notes
        mn.review_notes = review_notes
    mn.updated_at = datetime.now(UTC)

    existing = {a.id: a for a in db.scalars(select(ActionItem).where(ActionItem.meeting_id == meeting_id))}
    keep: set[str] = set()
    for pos, item in enumerate(data.action_items):
        row = existing.get(item.id or "")
        if row is None:
            row = ActionItem(meeting_id=meeting_id)
            db.add(row)
        values = item.model_dump(exclude={"id"})
        for k, v in values.items():
            setattr(row, k, v)
        row.position = pos
        db.flush()
        keep.add(row.id)
    for aid, row in existing.items():
        if aid not in keep:
            db.delete(row)
    db.commit()
    return minutes_out(db, meeting_id)  # type: ignore[return-value]


def update_action_status(db: Session, meeting_id: str, item_id: str, status: str) -> ActionItem:
    row = db.scalar(select(ActionItem).where(ActionItem.id == item_id, ActionItem.meeting_id == meeting_id))
    if row is None:
        raise NotFoundError("후속 업무를 찾을 수 없습니다.")
    row.status = status
    db.commit()
    return row


def list_action_items(db: Session, status: str | None = None, assignee: str | None = None, limit: int = 500) -> list[ActionItemWithMeeting]:
    order = case({"IN_PROGRESS": 0, "PENDING": 1, "DONE": 2}, value=ActionItem.status, else_=3)
    stmt = (
        select(ActionItem, Meeting.title, Meeting.meeting_date)
        .join(Meeting, Meeting.id == ActionItem.meeting_id)
        .order_by(order, Meeting.meeting_date.desc(), ActionItem.position)
        .limit(limit)
    )
    if status == "OPEN":
        stmt = stmt.where(ActionItem.status != "DONE")
    elif status:
        stmt = stmt.where(ActionItem.status == status)
    if assignee:
        stmt = stmt.where(ActionItem.assignee == assignee)
    return [
        ActionItemWithMeeting(**ActionItemOut.model_validate(a).model_dump(), meeting_id=a.meeting_id, meeting_title=title, meeting_date=d)
        for a, title, d in db.execute(stmt)
    ]


def dashboard(db: Session) -> DashboardOut:
    today = date.today()
    month_start = today.replace(day=1)
    titles = dict(db.execute(select(Meeting.id, Meeting.title)).all())
    active = db.scalars(
        select(Job).where(Job.status.in_([*ACTIVE_JOB_STATUSES, "FAILED"])).order_by(Job.updated_at.desc()).limit(20)
    ).all()
    # Only show a job if it is still the meeting's latest (a retried FAILED job is history).
    latest = dict(db.execute(select(Meeting.id, Meeting.latest_job_id)).all())
    active = [j for j in active if latest.get(j.meeting_id) == j.id][:5]
    docs = db.scalars(select(Document).order_by(Document.created_at.desc()).limit(5)).all()
    return DashboardOut(
        total_meetings=db.scalar(select(func.count()).select_from(Meeting)) or 0,
        meetings_this_month=db.scalar(select(func.count()).select_from(Meeting).where(Meeting.meeting_date >= month_start)) or 0,
        processing=db.scalar(select(func.count()).select_from(Meeting).where(Meeting.status.in_(ACTIVE_JOB_STATUSES), Meeting.latest_job_id.is_not(None))) or 0,
        open_action_items=db.scalar(select(func.count()).select_from(ActionItem).where(ActionItem.status != "DONE")) or 0,
        recent_meetings=[MeetingOut.model_validate(m) for m in db.scalars(select(Meeting).options(selectinload(Meeting.audio)).order_by(Meeting.created_at.desc()).limit(5))],
        active_jobs=[ActiveJobOut(meeting_title=titles.get(j.meeting_id, "-"), **_job_dict(j)) for j in active],
        recent_documents=[RecentDocumentOut(meeting_title=titles.get(d.meeting_id, "-"), meeting_id=d.meeting_id, filename=d.filename, size_bytes=d.size_bytes, created_at=d.created_at) for d in docs],
        recent_action_items=list_action_items(db, status="OPEN", limit=6),
    )


def _job_dict(j: Job) -> dict:
    return {k: getattr(j, k) for k in ("id", "meeting_id", "status", "progress", "message", "error", "created_at", "updated_at")}
