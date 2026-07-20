"""Scheduler semplice (APScheduler) con orari da config/jobs.yaml in ET.

Nessun monitoraggio continuo: solo i job giornalieri previsti.
Il job ai_extraction resta disabilitato finché l'AI non è configurata.
"""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings, jobs_config
from app.db import get_sessionmaker
from app.jobs.runner import JOB_REGISTRY

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _run_job(job_name: str) -> None:
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        fn = JOB_REGISTRY.get(job_name)
        if fn is None:
            logger.warning("Job sconosciuto: %s", job_name)
            return
        result = fn(db, "schedule")
        logger.info("Job %s completato: %s", job_name, result)
    except Exception:
        logger.exception("Job %s fallito", job_name)
        db.rollback()
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    settings = get_settings()
    cfg = jobs_config()
    tz = ZoneInfo(cfg["timezone_market"])
    scheduler = BackgroundScheduler(timezone=str(tz))
    for name, spec in cfg["jobs"].items():
        if not spec.get("enabled", False):
            continue
        if name == "ai_extraction" and not settings.ai_enabled:
            continue
        if name not in JOB_REGISTRY:
            continue
        scheduler.add_job(
            _run_job,
            CronTrigger(hour=spec["hour"], minute=spec["minute"],
                        day_of_week=spec.get("day_of_week", "*"), timezone=tz),
            args=[name], id=name, replace_existing=True,
        )
    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler avviato con %d job", len(scheduler.get_jobs()))
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
