"""Export Parquet/CSV via DuckDB per backtest e ricerca.

Gli export sono snapshot point-in-time: contengono le feature così come
erano al momento del segnale (feature_snapshots è immutabile per data)
e gli outcome calcolati solo dopo la chiusura della finestra.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import FeatureSnapshot, RetrospectiveOutcome, RiskScore, Security, SecurityListing


def export_dataset(db: Session, fmt: str = "parquet") -> Path:
    """Esporta il dataset segnali+outcome in Parquet o CSV. Ritorna il path."""
    if fmt not in ("parquet", "csv"):
        raise ValueError("Formato non supportato: usare 'parquet' o 'csv'")
    settings = get_settings()
    out_dir = Path(settings.data_dir) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"signals_{stamp}.{fmt}"

    rows = []
    scores = db.scalars(select(RiskScore)).all()
    for s in scores:
        sec = db.get(Security, s.security_id)
        listing = db.scalar(
            select(SecurityListing).where(SecurityListing.security_id == s.security_id)
            .order_by(SecurityListing.valid_from.desc()).limit(1)
        )
        snap = db.get(FeatureSnapshot, s.feature_snapshot_id) if s.feature_snapshot_id else None
        outcomes = db.scalars(
            select(RetrospectiveOutcome).where(RetrospectiveOutcome.risk_score_id == s.id)
        ).all()
        base = {
            "stable_id": sec.stable_id if sec else None,
            "ticker": listing.ticker if listing else None,
            "score_date": s.score_date.isoformat(),
            "risk_index": s.risk_index,
            "state": s.state,
            "confidence": s.confidence_grade,
            "squeeze_hazard": s.squeeze_hazard,
            "execution_hazard": s.execution_hazard,
            "scoring_version": s.scoring_version,
            "config_hash": s.config_hash,
            "features_json": json.dumps(snap.features if snap else {}, default=str),
        }
        for o in outcomes:
            rows.append({
                **base,
                "horizon_days": o.horizon_days,
                "reference_price": o.reference_price,
                "dd_intraday": o.dd_intraday,
                "dd_close": o.dd_close,
                "ret_close": o.ret_close,
                "ret_vs_benchmark": o.ret_vs_benchmark,
                "max_adverse_up": o.max_adverse_up,
                "hit_minus20": o.hit_minus20,
                "outcome_complete": o.complete,
            })
        if not outcomes:
            rows.append({**base, "horizon_days": None, "reference_price": None,
                         "dd_intraday": None, "dd_close": None, "ret_close": None,
                         "ret_vs_benchmark": None, "max_adverse_up": None,
                         "hit_minus20": None, "outcome_complete": False})

    if not rows:
        raise ValueError("Nessun segnale da esportare")

    # DuckDB legge il JSON intermedio da file (niente dipendenza pandas)
    tmp_json = out_dir / f".tmp_{stamp}.json"
    tmp_json.write_text(json.dumps(rows), encoding="utf-8")
    try:
        con = duckdb.connect()
        con.execute(
            "CREATE TABLE signals AS SELECT * FROM read_json_auto(?)", [str(tmp_json)]
        )
        if fmt == "parquet":
            con.execute(f"COPY signals TO '{out_path}' (FORMAT PARQUET)")
        else:
            con.execute(f"COPY signals TO '{out_path}' (FORMAT CSV, HEADER)")
        con.close()
    finally:
        tmp_json.unlink(missing_ok=True)
    return out_path
