"""Scheduler semplice (APScheduler) con orari da config/jobs.yaml in ET.

Nessun monitoraggio continuo: solo i job giornalieri previsti.
Il job ai_extraction resta disabilitato finché l'AI non è configurata.

Resilienza al sonno (per l'uso 24/7 su un Mac/laptop): oltre ai trigger cron,
in modalità live gira un CATCH-UP che, all'avvio e ogni 30 minuti, verifica
quali job del giorno non sono ancora stati completati e li esegue in ordine.
Così se la macchina era spenta/in sospensione all'orario previsto, al risveglio
il sistema si mette in pari da solo. I job sono idempotenti (chiave job+data):
eseguirli in ritardo è sicuro e non duplica nulla.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings, jobs_config
from app.db import get_sessionmaker
from app.jobs.runner import JOB_REGISTRY
from app.models import IngestionRun

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


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


# ------------------------------------------------------------- catch-up ---

def _job_due(spec: dict, now_et: datetime) -> bool:
    """Il job è previsto per oggi e l'orario ET è già passato?"""
    dow = spec.get("day_of_week")
    if dow:
        allowed = {_WEEKDAYS[d.strip().lower()] for d in str(dow).split(",")
                   if d.strip().lower() in _WEEKDAYS}
        if allowed and now_et.weekday() not in allowed:
            return False
    scheduled = now_et.replace(hour=spec["hour"], minute=spec["minute"],
                               second=0, microsecond=0)
    return now_et >= scheduled


def _job_succeeded(db: Session, name: str, key_date) -> bool:
    run = db.scalar(
        select(IngestionRun).where(
            IngestionRun.idempotency_key == f"{name}:{key_date.isoformat()}",
            IngestionRun.status.in_(["success", "partial"]),
        ).limit(1)
    )
    return run is not None


def due_jobs(db: Session, now_et: datetime, key_date, *,
             settings=None, cfg=None) -> list[str]:
    """Job abilitati, previsti per oggi, con orario passato e non ancora
    completati (in ordine di configurazione). Funzione pura e testabile."""
    settings = settings or get_settings()
    cfg = cfg or jobs_config()
    out: list[str] = []
    for name, spec in cfg["jobs"].items():
        if not spec.get("enabled", False):
            continue
        if name not in JOB_REGISTRY:
            continue
        if name == "ai_extraction" and not settings.ai_enabled:
            continue
        if not _job_due(spec, now_et):
            continue
        if _job_succeeded(db, name, key_date):
            continue
        out.append(name)
    return out


def _catch_up() -> None:
    """Esegue i job del giorno non ancora completati (resilienza al sonno)."""
    from app.seed.demo import last_business_day

    cfg = jobs_config()
    tz = ZoneInfo(cfg["timezone_market"])
    now_et = datetime.now(tz)
    key_date = last_business_day()

    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        pending = due_jobs(db, now_et, key_date)
    finally:
        db.close()

    if not pending:
        return
    logger.info("Catch-up: %d job da recuperare oggi: %s", len(pending), ", ".join(pending))
    for name in pending:  # in ordine di configurazione (universo -> ingest -> ranking...)
        _run_job(name)


# ------------------------------------------------------------ scheduler ---

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

    # catch-up SOLO in live (in demo i job sono no-op/veloci e non serve):
    # rende l'esecuzione 24/7 su Mac resiliente a sospensione/spegnimento.
    if settings.app_mode == "live":
        scheduler.add_job(
            _catch_up, IntervalTrigger(minutes=30, timezone=tz),
            id="_catch_up", replace_existing=True, max_instances=1, coalesce=True,
        )
        scheduler.add_job(
            _catch_up, DateTrigger(run_date=datetime.now(tz) + timedelta(seconds=10)),
            id="_catch_up_boot", replace_existing=True, max_instances=1,
        )

    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler avviato con %d job (catch-up: %s)",
                len(scheduler.get_jobs()), settings.app_mode == "live")
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
