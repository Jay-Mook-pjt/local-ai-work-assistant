from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status

from app.api.deps import DB
from app.schemas.meeting import GlossaryIn, GlossaryOut
from app.services import glossary_service

router = APIRouter(prefix="/api", tags=["glossary"])
TermId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def _err(exc: glossary_service.GlossaryError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


@router.get("/glossary", response_model=list[GlossaryOut])
def list_glossary(db: DB) -> list[GlossaryOut]:
    return [GlossaryOut.model_validate(t) for t in glossary_service.list_terms(db)]


@router.post("/glossary", response_model=GlossaryOut, status_code=status.HTTP_201_CREATED)
def create_term(body: GlossaryIn, db: DB) -> GlossaryOut:
    try:
        return GlossaryOut.model_validate(glossary_service.create(db, body))
    except glossary_service.GlossaryError as exc:
        raise _err(exc) from exc


@router.put("/glossary/{term_id}", response_model=GlossaryOut)
def update_term(term_id: TermId, body: GlossaryIn, db: DB) -> GlossaryOut:
    try:
        return GlossaryOut.model_validate(glossary_service.update(db, term_id, body))
    except glossary_service.GlossaryError as exc:
        raise _err(exc) from exc


@router.delete("/glossary/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_term(term_id: TermId, db: DB) -> Response:
    try:
        glossary_service.delete(db, term_id)
    except glossary_service.GlossaryError as exc:
        raise _err(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
