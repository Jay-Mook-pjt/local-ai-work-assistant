from typing import Annotated

from fastapi import Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Meeting
from app.services import meeting_service

DB = Annotated[Session, Depends(get_db)]
# Server-generated ids are 32 hex chars; rejecting anything else early also
# keeps ids safe to use in storage paths.
MeetingId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def load_meeting(db: DB, id: MeetingId) -> Meeting:
    try:
        return meeting_service.get_meeting(db, id)
    except meeting_service.NotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


MeetingDep = Annotated[Meeting, Depends(load_meeting)]
