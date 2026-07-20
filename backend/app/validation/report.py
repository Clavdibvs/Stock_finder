"""Auto-valutazione continua: il ranking batte le baseline?

Ogni settimana il sistema misura la propria precision@5/@10 (etichetta
primaria: DD_10 <= -20%) su TUTTI i segnali con finestra chiusa e la
confronta con le 9 baseline. Il risultato viene salvato con storico e, se il
sistema NON batte la miglior baseline, parte una notifica di drift.

Questo è l'"auto-miglioramento" onesto del progetto: accumulo di evidenza e
allarme quando l'evidenza è contraria. I pesi NON si auto-modificano mai
(pre-registrazione, VALIDATION.md): la ricalibrazione resta una decisione
umana ai phase gate, informata da questi numeri.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import PRIMARY_LABEL
from app.models import AppSetting, Notification, RetrospectiveOutcome, RiskScore, utcnow
from app.validation.baselines import ALL_BASELINES

logger = logging.getLogger(__name__)

REPORT_KEY = "validation_report"
MIN_SIGNALS = 10  # sotto questa soglia i numeri non sono interpretabili


def _dates_with_complete_outcomes(db: Session) -> list[date]:
    horizon = PRIMARY_LABEL["horizon"]
    rows = db.execute(
        select(RiskScore.score_date)
        .join(RetrospectiveOutcome, RetrospectiveOutcome.risk_score_id == RiskScore.id)
        .where(RetrospectiveOutcome.horizon_days == horizon,
               RetrospectiveOutcome.complete.is_(True))
        .distinct()
    ).scalars().all()
    return sorted(rows)


def _hits_for_date(db: Session, d: date) -> dict[int, bool]:
    """security_id -> etichetta primaria (DD_10 <= -20%) per i segnali del giorno."""
    horizon = PRIMARY_LABEL["horizon"]
    rows = db.execute(
        select(RetrospectiveOutcome.security_id, RetrospectiveOutcome.hit_minus20)
        .join(RiskScore, RiskScore.id == RetrospectiveOutcome.risk_score_id)
        .where(RiskScore.score_date == d,
               RetrospectiveOutcome.horizon_days == horizon,
               RetrospectiveOutcome.complete.is_(True),
               RetrospectiveOutcome.hit_minus20.is_not(None))
    ).all()
    return {sec_id: bool(hit) for sec_id, hit in rows}


def _system_ranking(db: Session, d: date) -> list[int]:
    return list(db.scalars(
        select(RiskScore.security_id)
        .where(RiskScore.score_date == d, RiskScore.risk_index.is_not(None))
        .order_by(RiskScore.risk_index.desc())
    ))


def _precision(ranking: list[int], hits: dict[int, bool], k: int) -> tuple[int, int]:
    """(hit, valutabili) sui primi k del ranking con outcome noto."""
    top = [s for s in ranking if s in hits][:k]
    return sum(1 for s in top if hits[s]), len(top)


def build_report(db: Session) -> dict:
    """Micro-media di precision@5/@10 su tutte le date con outcome completi."""
    dates = _dates_with_complete_outcomes(db)
    counters: dict[str, list[int]] = {}  # nome -> [hit, valutabili] cumulati

    def add(name: str, hit: int, n: int) -> None:
        acc = counters.setdefault(name, [0, 0])
        acc[0] += hit
        acc[1] += n

    total_signals = 0
    for d in dates:
        hits = _hits_for_date(db, d)
        if not hits:
            continue
        total_signals += len(hits)
        sys_rank = _system_ranking(db, d)
        for k in (5, 10):
            h, n = _precision(sys_rank, hits, k)
            add(f"system@{k}", h, n)
        for name, fn in ALL_BASELINES.items():
            try:
                rank = [r.security_id for r in fn(db, d)]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Baseline %s fallita per %s: %s", name, d, exc)
                continue
            h, n = _precision(rank, hits, 10)
            add(f"{name}@10", h, n)

    def ratio(name: str) -> float | None:
        acc = counters.get(name)
        if not acc or acc[1] == 0:
            return None
        return round(acc[0] / acc[1], 3)

    precisions = {name: ratio(name) for name in counters}
    baseline_vals = {n: v for n, v in precisions.items()
                     if n.endswith("@10") and not n.startswith("system") and v is not None}
    best_baseline = max(baseline_vals, key=baseline_vals.get) if baseline_vals else None
    system10 = precisions.get("system@10")
    lift = (round(system10 - baseline_vals[best_baseline], 3)
            if system10 is not None and best_baseline else None)

    return {
        "generated_at": utcnow().isoformat(),
        "dates_evaluated": len(dates),
        "signals_evaluated": total_signals,
        "interpretable": total_signals >= MIN_SIGNALS,
        "precision": precisions,
        "best_baseline": best_baseline,
        "lift_vs_best_baseline": lift,
        "label": f"DD_{PRIMARY_LABEL['horizon']} <= {PRIMARY_LABEL['threshold']:.0%}",
        "note": ("Campione insufficiente: i numeri non sono ancora interpretabili"
                 if total_signals < MIN_SIGNALS else
                 "Micro-media su tutte le date con finestra a 10 sedute chiusa"),
    }


def save_report(db: Session, report: dict) -> None:
    setting = db.get(AppSetting, REPORT_KEY)
    history = []
    if setting is not None and setting.value:
        history = setting.value.get("history", [])
    history = ([{k: report[k] for k in
                 ("generated_at", "signals_evaluated", "lift_vs_best_baseline")}]
               + history)[:52]  # un anno di storico settimanale
    payload = {"latest": report, "history": history}
    if setting is None:
        db.add(AppSetting(key=REPORT_KEY, value=payload))
    else:
        setting.value = payload
    db.flush()

    # drift alert: il sistema non batte la miglior baseline (campione valido)
    if report["interpretable"] and report["lift_vs_best_baseline"] is not None \
            and report["lift_vs_best_baseline"] < 0:
        key = f"validation_drift:{report['generated_at'][:10]}"
        exists = db.scalar(select(Notification).where(Notification.dedup_key == key))
        if exists is None:
            title = "Validazione: il ranking NON batte la miglior baseline"
            body = (f"precision@10 sistema {report['precision'].get('system@10')} vs "
                    f"{report['best_baseline']} {report['precision'].get(report['best_baseline'])} "
                    f"su {report['signals_evaluated']} segnali. Rivedere pesi/soglie al "
                    "prossimo phase gate (nessuna modifica automatica).")
            db.add(Notification(rule="validation_drift", title=title, body=body,
                                dedup_key=key))
            from app.core.notify import send_notification
            send_notification(title, body)
    db.flush()
