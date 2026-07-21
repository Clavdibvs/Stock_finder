"""Classificatore deterministico eventi news (senza AI): M&A, FDA, offering."""
from __future__ import annotations

from datetime import UTC, datetime

from app.adapters.news_events import classify_news_events
from app.models import Document, Event, Security


def _doc(db, sec_id, url, title, family=None, level=4, when=None):
    when = when or datetime.now(UTC)
    d = Document(security_id=sec_id, url_canonical=url, url_original=url,
                 title=title, source_level=level,
                 first_seen_at=when, published_at=when,
                 license_state="metadata_only")
    db.add(d)
    db.flush()
    d.duplicate_family_id = family or d.id
    d.is_duplicate = family is not None
    db.flush()
    return d


class TestNewsEventClassifier:
    def test_ma_from_two_origins_triggers_binary(self, db):
        """M&A da >=2 origini indipendenti -> evento binario pendente."""
        sec = Security(name="AtaiBeckley Inc.", is_demo=False)
        db.add(sec)
        db.flush()
        _doc(db, sec.id, "https://reuters.com/a", "AtaiBeckley to be acquired by Lilly in $3.8B deal", level=3)
        _doc(db, sec.id, "https://fool.com/b", "Why AtaiBeckley soared: takeover by Eli Lilly", level=5)
        r = classify_news_events(db, sec)
        assert r["events"] == 1
        from sqlalchemy import select
        ev = db.scalar(select(Event).where(Event.classified_by == "rule_news"))
        assert ev.event_type == "ma_rumor"
        assert ev.is_binary is True
        assert ev.status == "pending"
        assert ev.details["origins"] == 2

    def test_single_origin_not_enough_for_binary(self, db):
        """Un solo titolo M&A non basta (min 2 origini): niente evento binario."""
        sec = Security(name="Solo Corp", is_demo=False)
        db.add(sec)
        db.flush()
        _doc(db, sec.id, "https://x.com/a", "Solo Corp to acquire tiny startup", level=8)
        r = classify_news_events(db, sec)
        assert r["events"] == 0

    def test_duplicates_count_as_one_origin(self, db):
        """Cento riscritture della stessa notizia = una origine: non basta."""
        sec = Security(name="Dup Corp", is_demo=False)
        db.add(sec)
        db.flush()
        origin = _doc(db, sec.id, "https://origin.com/x", "Dup Corp nears deal to be acquired", level=3)
        for i in range(5):
            _doc(db, sec.id, f"https://copy{i}.com/x", "Dup Corp nears deal to be acquired",
                 family=origin.id, level=10)
        r = classify_news_events(db, sec)
        assert r["events"] == 0  # 6 documenti ma 1 sola origine

    def test_offering_needs_one_origin(self, db):
        sec = Security(name="Dilute Corp", is_demo=False)
        db.add(sec)
        db.flush()
        _doc(db, sec.id, "https://pr.com/a", "Dilute Corp prices $50M public offering", level=2)
        r = classify_news_events(db, sec)
        assert r["events"] == 1
        from sqlalchemy import select
        ev = db.scalar(select(Event).where(Event.event_type == "offering_or_dilution"))
        assert ev.is_binary is False

    def test_idempotent(self, db):
        sec = Security(name="Ide Corp", is_demo=False)
        db.add(sec)
        db.flush()
        _doc(db, sec.id, "https://a.com/1", "Ide Corp to be acquired in merger", level=3)
        _doc(db, sec.id, "https://b.com/2", "Ide Corp takeover talks advance", level=4)
        assert classify_news_events(db, sec)["events"] == 1
        assert classify_news_events(db, sec)["events"] == 0  # non ricrea

    def test_no_match_no_event(self, db):
        sec = Security(name="Quiet Corp", is_demo=False)
        db.add(sec)
        db.flush()
        _doc(db, sec.id, "https://a.com/1", "Quiet Corp reports steady quarterly revenue", level=4)
        _doc(db, sec.id, "https://b.com/2", "Analyst maintains rating on Quiet Corp", level=5)
        assert classify_news_events(db, sec)["events"] == 0

    def test_binary_gate_fires_end_to_end(self, db):
        """Con M&A news da 2 origini, lo scoring dà EVENTO BINARIO — EVITARE."""
        from datetime import date
        from app.candidates.features import compute_features
        from app.claims.graph import compute_narrative_stats
        from app.constants import STATE_BINARY_EVENT
        from app.models import MarketBar, SecurityListing
        from app.scoring.engine import compute_score
        from app.scoring.pipeline import build_event_context
        from app.seed.demo import business_days_back

        sec = Security(name="Target Corp", is_demo=False)
        db.add(sec)
        db.flush()
        db.add(SecurityListing(security_id=sec.id, ticker="TGT", exchange="NASDAQ",
                               status="active", valid_from=date(2026, 1, 1),
                               shares_outstanding=50_000_000))
        days = business_days_back(date(2026, 7, 20), 80)
        price = 5.0
        for i, d in enumerate(days):
            ret = 0.30 if i == len(days) - 1 else 0.001
            vol = 5_000_000 if i == len(days) - 1 else 400_000
            price *= (1 + ret)
            db.add(MarketBar(security_id=sec.id, bar_date=d, session="regular",
                             open=price / (1 + ret), high=price * 1.02, low=price * 0.98,
                             close=price, volume=vol, provider="test"))
        db.flush()
        news_ts = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)  # prima di _asof_ts
        _doc(db, sec.id, "https://reuters.com/tgt", "Target Corp to be acquired by BigPharma",
             level=3, when=news_ts)
        _doc(db, sec.id, "https://cnbc.com/tgt", "Target Corp nears deal, takeover imminent",
             level=4, when=news_ts)
        classify_news_events(db, sec)

        asof = date(2026, 7, 20)
        f = compute_features(db, sec.id, asof)
        n = compute_narrative_stats(db, sec.id)
        ctx = build_event_context(db, sec.id, asof)
        assert ctx.has_pending_binary is True
        result = compute_score(f, n, ctx)
        assert result.state == STATE_BINARY_EVENT
