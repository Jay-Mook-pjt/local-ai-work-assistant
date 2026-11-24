"""Central logging: console + rotating file under logs/."""

import logging
from logging.handlers import RotatingFileHandler

from app.config import Settings

_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"


def setup_logging(settings: Settings, filename: str = "backend.log") -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if getattr(root, "_lawa_configured", False):
        return
    root.setLevel(settings.log_level.upper())
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FORMAT))
    file_handler = RotatingFileHandler(
        settings.log_dir / filename, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console)
    root.addHandler(file_handler)
    root._lawa_configured = True  # type: ignore[attr-defined]
