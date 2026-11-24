"""SQLite-backed job queue shared by the API (enqueue) and the worker (claim/update)."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Job, Meeting
from app.schemas.meeting import ACTIVE_JOB_STATUSES

log = logging.getLogger(__name__)


class JobConflictError(Exception):
    pass


def active_job(db: Session, meeting_id: str) -> Job | None:
    return db.scalar(select(Job).where(Job.meeting_id == meeting_id, Job.status.in_(ACTIVE_JOB_STATUSES)))


def enqueue(db: Session, meeting: Meeting, llm_model: str | None = None, retranscribe: bool = False) -> Job:
    """Queue an analysis job. Raises JobConflictError if one is already running."""
    if active_job(db, meeting.id):
        raise JobConflictError("이미 처리 중인 작업이 있습니다.")
    job = Job(meeting_id=meeting.id, status="PENDING", progress=0, message="처리 대기 중", llm_model=llm_model, retranscribe=retranscribe)
    db.add(job)
    db.flush()
    meeting.status = "PENDING"
    meeting.latest_job_id = job.id
    db.commit()
    log.info("Enqueued job %s for meeting %s", job.id, meeting.id)
    return job


def claim_next(db: Session, worker_id: str) -> Job | None:
    """Atomically move the oldest PENDING job to PREPROCESSING and return it.

    The conditional UPDATE (status still PENDING) makes this safe even if more
    than one worker runs.
    """
    candidate = db.scalar(select(Job.id).where(Job.status == "PENDING").order_by(Job.created_at).limit(1))
    if candidate is None:
        return None
    now = datetime.now(UTC)
    result = db.execute(
        update(Job)
        .where(Job.id == candidate, Job.status == "PENDING")
        .values(status="PREPROCESSING", progress=5, message="작업 시작", worker_id=worker_id, started_at=now, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        return None
    db.execute(update(Meeting).where(Meeting.id == db.get(Job, candidate).meeting_id).values(status="PREPROCESSING"))
    db.commit()
    job = db.get(Job, candidate)
    db.refresh(job)
    return job


def set_progress(db: Session, job: Job, status: str, progress: int, message: str | None = None) -> None:
    job.status = status
    job.progress = max(0, min(100, progress))
    job.message = message
    db.execute(update(Meeting).where(Meeting.id == job.meeting_id, Meeting.latest_job_id == job.id).values(status=status))
    db.commit()


def complete(db: Session, job: Job, message: str = "처리 완료") -> None:
    job.finished_at = datetime.now(UTC)
    set_progress(db, job, "COMPLETED", 100, message)


def fail(db: Session, job: Job, error: str) -> None:
    job.error = error[:4000]
    job.finished_at = datetime.now(UTC)
    set_progress(db, job, "FAILED", job.progress, None)
    log.warning("Job %s failed: %s", job.id, error)


def fail_interrupted(db: Session) -> int:
    """On worker start: jobs left mid-run by a crashed/stopped worker become FAILED (retryable)."""
    running = [s for s in ACTIVE_JOB_STATUSES if s != "PENDING"]
    jobs = db.scalars(select(Job).where(Job.status.in_(running))).all()
    for job in jobs:
        fail(db, job, "작업자가 처리 중에 중지되어 작업이 중단되었습니다. 다시 처리해 주세요.")
    return len(jobs)
