"""Project glossary: domain terms injected into STT and LLM prompts.

This is reference context, not model training — the local models are unchanged;
every new transcription/analysis simply receives the current glossary.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import GlossaryTerm
from app.schemas.meeting import GlossaryIn

MAX_PROMPT_TERMS = 60


class GlossaryError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def list_terms(db: Session) -> list[GlossaryTerm]:
    return list(db.scalars(select(GlossaryTerm).order_by(func.lower(GlossaryTerm.term))))


def _duplicate(db: Session, term: str, exclude_id: str | None = None) -> bool:
    stmt = select(GlossaryTerm.id).where(func.lower(GlossaryTerm.term) == term.lower())
    if exclude_id:
        stmt = stmt.where(GlossaryTerm.id != exclude_id)
    return db.scalar(stmt) is not None


def create(db: Session, data: GlossaryIn) -> GlossaryTerm:
    if _duplicate(db, data.term):
        raise GlossaryError(f"이미 등록된 용어입니다: {data.term}", 409)
    row = GlossaryTerm(term=data.term, description=data.description, aliases=data.aliases)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update(db: Session, term_id: str, data: GlossaryIn) -> GlossaryTerm:
    row = db.get(GlossaryTerm, term_id)
    if row is None:
        raise GlossaryError("용어를 찾을 수 없습니다.", 404)
    if _duplicate(db, data.term, exclude_id=term_id):
        raise GlossaryError(f"이미 등록된 용어입니다: {data.term}", 409)
    row.term, row.description, row.aliases = data.term, data.description, data.aliases
    db.commit()
    db.refresh(row)
    return row


def delete(db: Session, term_id: str) -> None:
    row = db.get(GlossaryTerm, term_id)
    if row is None:
        raise GlossaryError("용어를 찾을 수 없습니다.", 404)
    db.delete(row)
    db.commit()


def stt_terms(db: Session) -> list[str]:
    """Plain terms for Whisper's initial prompt (spelling hints)."""
    return [t.term for t in list_terms(db)][:MAX_PROMPT_TERMS]


def prompt_block(db: Session) -> str:
    """Markdown section appended to the LLM system prompt ('' when empty)."""
    terms = list_terms(db)[:MAX_PROMPT_TERMS]
    if not terms:
        return ""
    lines = [
        "# 프로젝트 용어집 (회의록 작성 시 참고)",
        "아래 용어는 이 사용자의 업무에서 쓰는 뜻이다. 전사문에서 이 용어(또는 잘못 인식된 표기)가 나오면 이 뜻에 맞게 해석하고, 회의록에는 '용어' 칸의 표기로 적는다.",
        "용어집은 해석을 돕는 참고 자료일 뿐이다. 회의에서 언급되지 않은 내용을 용어집에서 가져와 회의록에 추가하지 않는다.",
    ]
    for t in terms:
        alias = f" (음성 인식 시 '{', '.join(t.aliases)}'(으)로 들릴 수 있음)" if t.aliases else ""
        lines.append(f"- {t.term}: {t.description or '(설명 없음)'}{alias}")
    return "\n".join(lines)
