"""Runtime settings stored in the DB (app_settings), falling back to .env values."""

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting

LLM_MODEL = "llm_model"


def get(db: Session, key: str) -> str | None:
    row = db.get(AppSetting, key)
    return row.value if row else None


def set_value(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def llm_model(db: Session) -> tuple[str, str]:
    """(model, source) where source is 'user' (chosen in the UI) or 'env'."""
    v = get(db, LLM_MODEL)
    return (v, "user") if v else (get_settings().llm_model, "env")
