"""FastAPI entrypoint. Run: uvicorn app.main:app --host 127.0.0.1 --port 8000"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analysis, audio, documents, emails, health, jobs, meetings, settings as settings_api
from app.config import get_settings
from app.db.session import init_db
from app.logging_config import setup_logging

settings = get_settings()
setup_logging(settings)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    for sub in ("audio/original", "audio/processed", "transcripts", "minutes", "exports"):
        (settings.storage_dir / sub).mkdir(parents=True, exist_ok=True)
    init_db()
    log.info("Backend started (env=%s, llm=%s)", settings.app_env, settings.llm_model)
    yield
    log.info("Backend stopped")


app = FastAPI(title="Personal AI Work Assistant", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (health.router, meetings.router, audio.router, analysis.router, jobs.router, settings_api.router, documents.router, emails.router):
    app.include_router(r)
