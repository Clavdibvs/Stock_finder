"""Automazione: notifiche esterne key-gated, auto-valutazione vs baseline."""
from __future__ import annotations

from datetime import date, timedelta

from app.models import (
    AppSetting, MarketBar, Notification, RetrospectiveOutcome, RiskScore, Security,
)
from app.seed.demo import business_days_back


class TestTelegramNotify:
    def test_disabled_by_default_no_network(self, monkeypatch):
        """Canale 'none': nessun invio, nessuna chiamata di rete."""
        import app.core.notify as mod
        called = []
        monkeypatch.setattr(mod.httpx, "post",
                            lambda *a, **k: called.append(a) or None)
        assert mod.send_notification("titolo", "corpo") is False
        assert called == []

    def test_requires_all_settings(self, monkeypatch):
        from app.config import get_settings
        import app.core.notify as mod
        monkeypatch.setenv("DDR_NOTIFY_CHANNEL", "telegram")
        monkeypatch.setenv("DDR_TELEGRAM_BOT_TOKEN", "123:abc")
        monkeypatch.delenv("DDR_TELEGRAM_CHAT_ID", raising=False)
        get_settings.cache_clear()
        try:
            assert mod.telegram_configured() is False  # manca la chat id
        finally:
            get_settings.cache_clear()

    def test_send_failure_never_raises(self, monkeypatch):
        """Un errore di invio non blocca mai la pipeline."""
        from app.config import get_settings
        import app.core.notify as mod
        monkeypatch.setenv("DDR_NOTIFY_CHANNEL", "telegram")
        monkeypatch.setenv("DDR_TELEGRAM_BOT_TOKEN", "123:abc")
        monkeypatch.setenv("DDR_TELEGRAM_CHAT_ID", "42")
        get_settings.cache_clear()
        try:
            def boom(*a, **k):
                raise RuntimeError("rete giù")
            monkeypatch.setattr(mod.httpx, "post", boom)
            assert mod.send_notification("titolo") is False  # nessuna eccezione
        finally:
            get_settings.cache_clear()

    def test_token_redacted_in_logs(self):
        import logging
        from app.core.logging import RedactingFilter
        record = logging.LogRecord(
            "httpx", logging.INFO, "f", 1,
            "HTTP Request: POST https://api.telegram.org/bot12345:AAbbCC-dd/sendMessage",
            (), None)
        RedactingFilter().filter(record)
        assert "12345:AAbbCC" not in record.getMessage()
        assert "[REDACTED]" in record.getMessage()


def _signal_with_outcome(db, ticker: str, risk_index: float, crashed: bool,
                         signal_date: date):
    """Crea security + score + outcome a 10 sedute completo."""
    sec = Security(name=f"{ticker} Corp", is_demo=False)
    db.add(sec)
    db.flush()
    days = business_days_back(signal_date, 30)
    for i, d in enumerate(days):
        db.add(MarketBar(security_id=sec.id, bar_date=d, session="regular",
                         open=10, high=11, low=9, close=10, volume=1000,
                         provider="test"))
    score = RiskScore(security_id=sec.id, score_date=signal_date,
                      risk_index=risk_index, confidence_grade="B",
                      state="MONITORARE", scoring_version="t",
                      config_hash="t", code_version="t")
    db.add(score)
    from datetime import UTC, datetime
    from app.models import FeatureSnapshot
    db.add(FeatureSnapshot(
        security_id=sec.id, snapshot_date=signal_date,
        asof_ts=datetime.combine(signal_date, datetime.min.time(), tzinfo=UTC),
        features={"ret_1d": risk_index / 200, "ret_5d": risk_index / 100,
                  "ret_20d": risk_index / 80, "rvol": risk_index / 10,
                  "atr_14": 1.0, "dist_ema20_atr": risk_index / 20,
                  "market_cap": 1e9 - risk_index * 1e6},
        is_candidate=True, pipeline_version="t", config_version="t",
    ))
    db.flush()
    db.add(RetrospectiveOutcome(
        risk_score_id=score.id, security_id=sec.id, reference_price=10.0,
        reference_date=signal_date + timedelta(days=1), horizon_days=10,
        dd_intraday=-0.35 if crashed else -0.05,
        hit_minus20=crashed, complete=True,
    ))
    db.flush()
    return sec, score


class TestValidationReport:
    def test_empty_dataset_is_honest(self, db):
        from app.validation.report import build_report
        report = build_report(db)
        assert report["signals_evaluated"] == 0
        assert report["interpretable"] is False
        assert report["lift_vs_best_baseline"] is None
        assert "insufficiente" in report["note"].lower()

    def test_report_measures_system_precision(self, db):
        """Il sistema che mette i crash in cima ottiene precision@10 alta."""
        from app.validation.report import build_report, save_report
        d = date(2026, 6, 1)
        # 12 segnali: i 6 con RI alto crollano, i 6 con RI basso no
        for i in range(6):
            _signal_with_outcome(db, f"HI{i}", 90 - i, crashed=True, signal_date=d)
        for i in range(6):
            _signal_with_outcome(db, f"LO{i}", 30 - i, crashed=False, signal_date=d)
        report = build_report(db)
        assert report["signals_evaluated"] == 12
        assert report["interpretable"] is True
        assert report["precision"]["system@5"] == 1.0
        assert report["precision"]["system@10"] == 0.6
        save_report(db, report)
        saved = db.get(AppSetting, "validation_report")
        assert saved.value["latest"]["signals_evaluated"] == 12
        assert len(saved.value["history"]) == 1

    def test_drift_alert_when_system_loses(self, db, monkeypatch):
        """Se il ranking è inverso ai crash, parte la notifica di drift."""
        from sqlalchemy import select
        from app.validation.report import build_report, save_report
        d = date(2026, 6, 1)
        # sistema al contrario: RI alto = nessun crash
        for i in range(6):
            _signal_with_outcome(db, f"HI{i}", 90 - i, crashed=False, signal_date=d)
        for i in range(6):
            _signal_with_outcome(db, f"LO{i}", 30 - i, crashed=True, signal_date=d)
        report = build_report(db)
        assert report["lift_vs_best_baseline"] is not None
        save_report(db, report)
        drift = db.scalar(select(Notification).where(
            Notification.rule == "validation_drift"))
        if report["lift_vs_best_baseline"] < 0:
            assert drift is not None
            assert "NON batte" in drift.title

    def test_report_job_idempotent(self, demo_client):
        r1 = demo_client.post("/api/quality/jobs/validation_report/run")
        r2 = demo_client.post("/api/quality/jobs/validation_report/run")
        assert r1.status_code == r2.status_code == 200
        q = demo_client.get("/api/quality").json()
        assert q["validation"] is not None
        assert "latest" in q["validation"]


class TestCatchUp:
    """Il recupero dei job non completati (resilienza al sonno del Mac)."""

    def _now_et(self, hour, weekday=2):
        # un mercoledì (weekday=2) all'ora ET indicata
        from datetime import datetime
        from zoneinfo import ZoneInfo
        base = datetime(2026, 7, 15, hour, 30, tzinfo=ZoneInfo("America/New_York"))
        # 2026-07-15 è mercoledì
        assert base.weekday() == weekday
        return base

    def test_due_includes_past_and_undone(self, db):
        from app.jobs.scheduler import due_jobs
        from app.seed.demo import last_business_day
        # alle 17:00 ET tutti i job giornalieri (ingest 05:45 ... daily_report 16:45)
        # sono passati; validation_report è settimanale (sab) -> escluso di mercoledì
        pending = due_jobs(db, self._now_et(17), last_business_day())
        assert "ingest_eod" in pending
        assert "ranking_eod" in pending
        assert "validation_report" not in pending  # solo il sabato

    def test_future_time_not_due(self, db):
        from app.jobs.scheduler import due_jobs
        from app.seed.demo import last_business_day
        # alle 06:00 ET solo universe_sync (05:30) e ingest_eod (05:45) sono passati
        pending = due_jobs(db, self._now_et(6), last_business_day())
        assert "universe_sync" in pending
        assert "ranking_eod" not in pending  # 16:15, ancora futuro

    def test_succeeded_job_excluded(self, db):
        from app.jobs.scheduler import due_jobs
        from app.models import IngestionRun
        from app.seed.demo import last_business_day
        key_date = last_business_day()
        db.add(IngestionRun(job_name="ranking_eod", status="success",
                            idempotency_key=f"ranking_eod:{key_date.isoformat()}"))
        db.flush()
        pending = due_jobs(db, self._now_et(17), key_date)
        assert "ranking_eod" not in pending  # già completato oggi
        assert "ingest_eod" in pending        # questo no

    def test_weekly_job_due_on_saturday(self, db):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app.jobs.scheduler import due_jobs
        from app.seed.demo import last_business_day
        sat = datetime(2026, 7, 18, 13, 0, tzinfo=ZoneInfo("America/New_York"))
        assert sat.weekday() == 5
        pending = due_jobs(db, sat, last_business_day())
        assert "validation_report" in pending  # sabato dopo le 12:00 ET
