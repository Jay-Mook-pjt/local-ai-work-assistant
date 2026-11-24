"""Request/response schemas. Field names match frontend/src/types/meeting.ts."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

JobStatus = Literal["PENDING", "UPLOADED", "PREPROCESSING", "TRANSCRIBING", "ANALYZING", "GENERATING", "COMPLETED", "FAILED"]
ActionStatus = Literal["PENDING", "IN_PROGRESS", "DONE"]
ACTIVE_JOB_STATUSES = ("PENDING", "PREPROCESSING", "TRANSCRIBING", "ANALYZING", "GENERATING")
UNKNOWN = "미확인"


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _clean_list(v: list[str]) -> list[str]:
    return [s.strip() for s in v if s and s.strip()]


# ---- Meetings ---------------------------------------------------------------


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    meeting_date: date
    attendees: list[str] = Field(default_factory=list, max_length=100)
    purpose: str = Field(default="", max_length=2000)
    agenda: list[str] = Field(default_factory=list, max_length=50)
    instructions: str = Field(default="", max_length=2000)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("회의 제목을 입력하세요.")
        return v

    @field_validator("attendees", "agenda")
    @classmethod
    def _strip_items(cls, v: list[str]) -> list[str]:
        v = _clean_list(v)
        if any(len(s) > 300 for s in v):
            raise ValueError("항목은 300자 이내로 입력하세요.")
        return v


class AudioFileOut(ORM):
    filename: str = Field(validation_alias="original_filename")
    size_bytes: int
    duration_seconds: float | None
    mime_type: str


class MeetingOut(ORM):
    id: str
    title: str
    meeting_date: date
    attendees: list[str]
    purpose: str
    agenda: list[str]
    instructions: str
    audio: AudioFileOut | None
    status: JobStatus
    latest_job_id: str | None
    created_at: datetime
    updated_at: datetime


class JobOut(ORM):
    id: str
    meeting_id: str
    status: JobStatus
    progress: int
    message: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


# ---- Transcript ---------------------------------------------------------------


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    speaker: str | None = None


class TranscriptOut(ORM):
    meeting_id: str
    language: str
    model: str
    segments: list[TranscriptSegment]
    created_at: datetime


# ---- Minutes ------------------------------------------------------------------


class DiscussionItem(BaseModel):
    topic: str = Field(default="", max_length=500)
    content: str = Field(default="", max_length=5000)
    speaker: str = Field(default=UNKNOWN, max_length=200)
    timestamp: str = Field(default=UNKNOWN, max_length=20)


class Decision(BaseModel):
    content: str = Field(max_length=2000)
    evidence: str = Field(default="", max_length=2000)
    timestamp: str = Field(default=UNKNOWN, max_length=20)


class ActionItemIn(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    task: str = Field(min_length=1, max_length=2000)
    assignee: str = Field(default=UNKNOWN, max_length=200)
    deadline: str = Field(default=UNKNOWN, max_length=200)
    status: ActionStatus = "PENDING"
    evidence: str = Field(default="", max_length=2000)
    timestamp: str = Field(default=UNKNOWN, max_length=20)

    @field_validator("assignee", "deadline", "timestamp")
    @classmethod
    def _blank_is_unknown(cls, v: str) -> str:
        return v.strip() or UNKNOWN


class ActionItemOut(ORM):
    id: str
    task: str
    assignee: str
    deadline: str
    status: ActionStatus
    evidence: str
    timestamp: str


class MinutesUpdate(BaseModel):
    meeting_summary: str = Field(min_length=1, max_length=20000)
    discussion_items: list[DiscussionItem] = Field(default_factory=list, max_length=200)
    decisions: list[Decision] = Field(default_factory=list, max_length=200)
    action_items: list[ActionItemIn] = Field(default_factory=list, max_length=200)
    open_issues: list[str] = Field(default_factory=list, max_length=200)
    next_meeting_checks: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("open_issues", "next_meeting_checks")
    @classmethod
    def _strip(cls, v: list[str]) -> list[str]:
        return _clean_list(v)


class MinutesOut(BaseModel):
    meeting_id: str
    meeting_summary: str
    discussion_items: list[DiscussionItem]
    decisions: list[Decision]
    action_items: list[ActionItemOut]
    open_issues: list[str]
    next_meeting_checks: list[str]
    llm_model: str
    edited: bool
    updated_at: datetime


class ActionItemStatusUpdate(BaseModel):
    status: ActionStatus


class ActionItemWithMeeting(ActionItemOut):
    meeting_id: str
    meeting_title: str
    meeting_date: date


# ---- Documents / email history (written in PHASE 5) -------------------------


class DocumentOut(ORM):
    meeting_id: str
    filename: str
    size_bytes: int
    created_at: datetime


class EmailHistoryOut(ORM):
    id: str
    meeting_id: str
    to: list[str]
    subject: str
    status: Literal["SENT", "FAILED"]
    error: str | None
    sent_at: datetime


# ---- Dashboard ---------------------------------------------------------------


class ActiveJobOut(JobOut):
    meeting_title: str


class RecentDocumentOut(DocumentOut):
    meeting_title: str


class DashboardOut(BaseModel):
    total_meetings: int
    meetings_this_month: int
    processing: int
    open_action_items: int
    recent_meetings: list[MeetingOut]
    active_jobs: list[ActiveJobOut]
    recent_documents: list[RecentDocumentOut]
    recent_action_items: list[ActionItemWithMeeting]
