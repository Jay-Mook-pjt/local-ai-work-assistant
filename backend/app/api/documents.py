from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Path, Response, status
from fastapi.responses import FileResponse

from app.api.deps import DB, MeetingDep
from app.models import Document
from app.schemas.meeting import DocumentOut
from app.services import document_service, storage

router = APIRouter(prefix="/api", tags=["documents"])
DocId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def _load(db: DB, doc_id: str) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    return doc


@router.post("/meetings/{id}/export", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def export_docx(meeting: MeetingDep, db: DB) -> DocumentOut:
    """Creates a DOCX from the current (possibly edited) minutes."""
    try:
        return DocumentOut.model_validate(document_service.export(db, meeting))
    except document_service.DocumentError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/documents/{doc_id}/download")
def download(doc_id: DocId, db: DB) -> FileResponse:
    doc = _load(db, doc_id)
    path = storage.resolve(doc.stored_path)
    if not path.exists():
        raise HTTPException(410, "문서 파일이 삭제되었습니다. 다시 생성하세요.")
    # RFC 5987 so Korean filenames survive in every browser.
    disposition = f"attachment; filename=\"meeting-minutes.docx\"; filename*=UTF-8''{quote(doc.filename)}"
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": disposition},
    )


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: DocId, db: DB) -> Response:
    document_service.delete(db, _load(db, doc_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
