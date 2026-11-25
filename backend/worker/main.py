"""Single background worker: polls the SQLite job queue and runs the pipeline.

Run from backend/:  .venv/bin/python -m worker.main
"""

import app.offline  # noqa: F401, I001 - must precede any model-library import

import logging
import os
import signal
import socket
import threading

from app.config import get_settings
from app.db.session import SessionLocal, init_db
from app.logging_config import setup_logging
from app.services import job_service
from worker import pipeline

log = logging.getLogger("worker")
stop = threading.Event()


def run_once(worker_id: str) -> bool:
    """Claim and process one job. Returns True if a job was processed."""
    with SessionLocal() as db:
        job = job_service.claim_next(db, worker_id)
        if job is None:
            return False
        log.info("Claimed job %s (meeting %s)", job.id, job.meeting_id)
        pipeline.run(db, job)
        log.info("Job %s finished with %s", job.id, job.status)
        return True


def main() -> None:
    settings = get_settings()
    setup_logging(settings, filename="worker.log")
    init_db()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    with SessionLocal() as db:
        n = job_service.fail_interrupted(db)
        if n:
            log.warning("Marked %d interrupted job(s) as FAILED", n)

    log.info("Worker %s started (poll every %.1fs)", worker_id, settings.worker_poll_seconds)
    while not stop.is_set():
        try:
            if not run_once(worker_id):
                stop.wait(settings.worker_poll_seconds)
        except Exception:  # noqa: BLE001 - keep the worker alive (e.g. DB briefly locked)
            log.exception("Worker loop error")
            stop.wait(settings.worker_poll_seconds)
    log.info("Worker stopped")


if __name__ == "__main__":
    main()
