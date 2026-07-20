"""Feature engine deterministico.

Regole non negoziabili:
- point-in-time: solo barre con bar_date <= asof_date (nessun look-ahead);
- un dato mancante resta None, mai 0;
- corporate action non riconciliata -> il titolo viene bloccato (feature nulle
  + flag), nessun segnale.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import candidates_config
from app.models import CorporateAction, Document, Event, MarketBar, SecurityListing


@dataclass
class Features:
    """Tutti i campi sono Opzionali: None significa 'mancante', mai zero."""
    asset_type: str = "equity"   # equity | crypto (regole di universo diverse)
    price: float | None = None
    ret_1d: float | None = None
    ret_5d: float | None = None
    ret_20d: float | None = None
    gap: float | None = None
    robust_z_ret: float | None = None
    rvol: float | None = None
    turnover_float: float | None = None
    dollar_volume: float | None = None
    median_dollar_volume_20d: float | None = None
    atr_14: float | None = None
    dist_ema20_atr: float | None = None
    market_cap: float | None = None
    float_shares: float | None = None
    shares_outstanding: float | None = None
    attention_docs_1d: int | None = None
    attention_z: float | None = None
    short_interest_pct_float: float | None = None
    days_to_cover: float | None = None
    volume_over_float: float | None = None
    premarket_gap: float | None = None
    halts_recent: int | None = None
    new_material_event: bool | None = None
    bars_available: int = 0
    stale_days: int | None = None
    blocked_unreconciled_action: bool = False
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        return d


def robust_z(value: float, history: list[float], mad_scale: float = 1.4826) -> float | None:
    """z robusto = (x - mediana) / (1.4826 * MAD). None se la storia è degenerata."""
    if len(history) < 3:
        return None
    med = statistics.median(history)
    mad = statistics.median([abs(x - med) for x in history])
    if mad == 0:
        return None
    return (value - med) / (mad_scale * mad)


def _bars_asof(db: Session, security_id: int, asof: date, limit: int = 300) -> list[MarketBar]:
    rows = db.scalars(
        select(MarketBar)
        .where(MarketBar.security_id == security_id,
               MarketBar.bar_date <= asof,
               MarketBar.session == "regular")
        .order_by(MarketBar.bar_date.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def _premarket_bar(db: Session, security_id: int, asof: date) -> MarketBar | None:
    return db.scalar(
        select(MarketBar)
        .where(MarketBar.security_id == security_id,
               MarketBar.bar_date == asof,
               MarketBar.session == "premarket")
    )


def compute_features(db: Session, security_id: int, asof: date) -> Features:
    from app.models import Security
    cfg = candidates_config()
    f = Features()
    sec = db.get(Security, security_id)
    if sec is not None and sec.security_type == "crypto":
        f.asset_type = "crypto"

    # blocco per corporate action non riconciliata
    unreconciled = db.scalar(
        select(CorporateAction)
        .where(CorporateAction.security_id == security_id,
               CorporateAction.reconciled.is_(False),
               CorporateAction.effective_date <= asof)
        .limit(1)
    )
    if unreconciled is not None:
        f.blocked_unreconciled_action = True
        f.missing.append("corporate_action_unreconciled")
        return f

    bars = _bars_asof(db, security_id, asof)
    f.bars_available = len(bars)
    if not bars:
        f.missing.extend(["price", "ret_1d", "ret_5d", "ret_20d", "rvol"])
        return f

    last = bars[-1]
    f.stale_days = (asof - last.bar_date).days
    closes = [b.close for b in bars if b.close is not None]
    volumes = [b.volume for b in bars if b.volume is not None]

    if last.close is not None:
        f.price = last.close
    else:
        f.missing.append("price")

    def ret(n: int) -> float | None:
        if len(closes) > n and closes[-1] is not None and closes[-1 - n]:
            return closes[-1] / closes[-1 - n] - 1
        return None

    f.ret_1d, f.ret_5d, f.ret_20d = ret(1), ret(5), ret(20)
    for name, v in (("ret_1d", f.ret_1d), ("ret_5d", f.ret_5d), ("ret_20d", f.ret_20d)):
        if v is None:
            f.missing.append(name)

    # gap: apertura di oggi vs chiusura precedente
    if len(bars) >= 2 and bars[-1].open is not None and bars[-2].close:
        f.gap = bars[-1].open / bars[-2].close - 1
    else:
        f.missing.append("gap")

    # robust z del rendimento giornaliero su finestra 252
    rz_cfg = cfg["robust_z"]
    if len(closes) >= rz_cfg["min_history"] and f.ret_1d is not None:
        rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))
                if closes[i - 1]]
        window = rets[-rz_cfg["window"]:]
        f.robust_z_ret = robust_z(f.ret_1d, window, rz_cfg["mad_scale"])
    if f.robust_z_ret is None:
        f.missing.append("robust_z_ret")

    # RVOL: volume odierno / mediana 20 sedute precedenti
    if len(volumes) >= 21 and volumes[-1] is not None:
        median20 = statistics.median(volumes[-21:-1])
        if median20 > 0:
            f.rvol = volumes[-1] / median20
    if f.rvol is None:
        f.missing.append("rvol")

    # dollar volume e mediana 20g
    if last.close is not None and last.volume is not None:
        f.dollar_volume = last.close * last.volume
    dollar_vols = [b.close * b.volume for b in bars[-20:]
                   if b.close is not None and b.volume is not None]
    if len(dollar_vols) >= 10:
        f.median_dollar_volume_20d = statistics.median(dollar_vols)
    else:
        f.missing.append("median_dollar_volume_20d")

    # ATR(14) e distanza da EMA20 in ATR
    if len(bars) >= 15:
        trs = []
        for i in range(1, len(bars)):
            b, prev = bars[i], bars[i - 1]
            if None in (b.high, b.low, prev.close):
                continue
            trs.append(max(b.high - b.low, abs(b.high - prev.close), abs(b.low - prev.close)))
        if len(trs) >= 14:
            f.atr_14 = statistics.fmean(trs[-14:])
    if f.atr_14 and len(closes) >= 20 and f.price is not None:
        k = 2 / 21
        ema = closes[-20]
        for c in closes[-19:]:
            ema = c * k + ema * (1 - k)
        if f.atr_14 > 0:
            f.dist_ema20_atr = (f.price - ema) / f.atr_14

    # anagrafica point-in-time: shares/float dal listing valido alla data
    listing = db.scalar(
        select(SecurityListing)
        .where(SecurityListing.security_id == security_id,
               SecurityListing.valid_from <= asof)
        .order_by(SecurityListing.valid_from.desc())
        .limit(1)
    )
    if listing is not None:
        f.shares_outstanding = listing.shares_outstanding
        f.float_shares = listing.float_shares
    if f.shares_outstanding and f.price is not None:
        f.market_cap = f.shares_outstanding * f.price
    else:
        f.missing.append("market_cap")
    if f.float_shares and last.volume is not None and f.float_shares > 0:
        f.turnover_float = last.volume / f.float_shares
        f.volume_over_float = f.turnover_float
    else:
        f.missing.append("turnover_float")

    # pre-market ritardato (se disponibile)
    pm = _premarket_bar(db, security_id, asof)
    if pm is not None and pm.close is not None and last.close:
        # gap pre-market vs ultima chiusura regolare precedente al giorno asof
        prev_close = bars[-2].close if (bars[-1].bar_date == asof and len(bars) >= 2) else last.close
        if prev_close:
            f.premarket_gap = pm.close / prev_close - 1

    # attenzione: TUTTI i documenti visti nel giorno (le copie contano per
    # l'attenzione; per la conferma contano solo le origini indipendenti)
    has_docs = db.scalar(
        select(Document.id).where(Document.security_id == security_id).limit(1)
    )
    if has_docs is not None:
        counts = _daily_doc_counts(db, security_id, asof, days=60)
        f.attention_docs_1d = counts[-1] if counts else None
        if counts and len(counts) >= 10 and counts[-1] is not None:
            f.attention_z = robust_z(float(counts[-1]), [float(c) for c in counts[:-1]])
    if f.attention_z is None:
        f.missing.append("attention_z")

    # short interest point-in-time dal listing (fonte FINRA, bimensile);
    # se assente resta None: squeeze "sconosciuto", mai zero
    if listing is not None and listing.short_interest_shares is not None:
        if f.float_shares:
            f.short_interest_pct_float = listing.short_interest_shares / f.float_shares
        adv20 = None
        if len(volumes) >= 20:
            adv20 = statistics.fmean(volumes[-20:])
        if adv20:
            f.days_to_cover = listing.short_interest_shares / adv20

    # nuovo evento materiale classificato alla data
    ev = db.scalar(
        select(Event)
        .where(Event.security_id == security_id,
               Event.materiality == "high",
               Event.announced_at.is_not(None))
        .order_by(Event.announced_at.desc())
        .limit(1)
    )
    if ev is not None and ev.announced_at is not None:
        f.new_material_event = ev.announced_at.date() >= _n_days_before(asof, 1)
    else:
        f.new_material_event = None

    # short interest: resta None se non fornito (mai 0 di default)
    if f.short_interest_pct_float is None:
        f.missing.append("short_interest_pct_float")

    return f


def _daily_doc_counts(db: Session, security_id: int, asof: date, days: int) -> list[int]:
    rows = db.scalars(
        select(Document).where(Document.security_id == security_id)
    ).all()
    from datetime import timedelta
    counts = []
    for i in range(days - 1, -1, -1):
        day = asof - timedelta(days=i)
        counts.append(sum(
            1 for d in rows
            if d.first_seen_at is not None and d.first_seen_at.date() == day
        ))
    return counts


def _n_days_before(asof: date, n: int) -> date:
    from datetime import timedelta
    return asof - timedelta(days=n)
