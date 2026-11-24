from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from app.api.deps import DB
from app.models import Job
from app.schemas.meeting import JobOut

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs/{id}", response_model=JobOut)
def get_job(id: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")], db: DB) -> JobOut:
    job = db.get(Job, id)
    if job is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return JobOut.model_validate(job)
