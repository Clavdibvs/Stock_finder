"""Look-ahead e timestamp: published_at vs first_seen_at, point-in-time."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from app.claims.graph import compute_narrative_stats
from app.models import Claim, Document, MarketBar, Security
from app.seed.demo import business_days_back


def _sec(db, name="PIT Corp"):
    sec = Security(name=name, is_demo=True)
    db.add(sec)
    db.flush()
    return sec


def _ts(d: date, h: int = 12) -> datetime:
    return datetime.combine(d, time(h, 0), tzinfo=UTC)


class TestTimestampSeparation:
    def test_published_and_first_seen_are_distinct(self, db):
        """Una notizia pubblicata ieri ma vista oggi conserva entrambe le date."""
        sec = _sec(db)
        published = datetime(2026, 7, 10, 14, 0, tzinfo=UTC)
        seen = datetime(2026, 7, 12, 8, 30, tzinfo=UTC)
        doc = Document(security_id=sec.id, url_canonical="https://a.com/x",
                       title="Notizia", published_at=published, first_seen_at=seen,
                       source_level=4)
        db.add(doc)
        db.flush()
        assert doc.published_at == published
        assert doc.first_seen_at == seen
        assert doc.first_seen_at != doc.published_at


class TestNoLookAhead:
    def test_future_documents_excluded_from_pit_stats(self, db):
        """Un documento visto DOPO asof non entra nelle statistiche point-in-time.

        Caso concreto: rumor al giorno T, smentita a T+3. Lo score calcolato
        a T non deve conoscere la smentita.
        """
        sec = _sec(db)
        t0 = datetime(2026, 6, 1, 15, 0, tzinfo=UTC)
        rumor_doc = Document(security_id=sec.id, url_canonical="https://r.com/1",
                             title="Rumor", first_seen_at=t0, published_at=t0,
                             source_level=6)
        db.add(rumor_doc)
        db.flush()
        denial_doc = Document(security_id=sec.id, url_canonical="https://ir.com/denial",
                              title="Smentita ufficiale con testo differente",
                              first_seen_at=t0 + timedelta(days=3),
                              published_at=t0 + timedelta(days=3), source_level=2)
        db.add(denial_doc)
        db.flush()
        db.add(Claim(security_id=sec.id, subject="A", predicate="comprerebbe", object="B",
                     status="rumor", evidence_span="span di prova sufficiente",
                     source_document_id=rumor_doc.id))
        db.add(Claim(security_id=sec.id, subject="B", predicate="smentisce", object="trattative",
                     status="fatto", confirmation_level=2,
                     evidence_span="la società smentisce ufficialmente",
                     source_document_id=denial_doc.id))
        db.flush()

        pit = compute_narrative_stats(db, sec.id, asof_ts=t0 + timedelta(hours=1))
        assert pit.total_documents == 1
        assert pit.primary_sources == 0
        assert pit.central_claim_status == "rumor"  # la smentita non esiste ancora

        full = compute_narrative_stats(db, sec.id)
        assert full.total_documents == 2
        assert full.central_claim_status == "fatto"

    def test_features_use_only_past_bars(self, db):
        """Le feature a una data non usano barre successive."""
        from app.candidates.features import compute_features
        sec = _sec(db)
        days = business_days_back(date(2026, 6, 30), 80)
        for i, d in enumerate(days):
            price = 10.0 + i * 0.01
            db.add(MarketBar(security_id=sec.id, bar_date=d, session="regular",
                             open=price, high=price * 1.01, low=price * 0.99,
                             close=price, volume=100_000, provider="test"))
        # barra futura estrema che NON deve influire
        future_day = days[-1] + timedelta(days=1)
        db.add(MarketBar(security_id=sec.id, bar_date=future_day, session="regular",
                         open=50.0, high=60.0, low=45.0, close=55.0,
                         volume=9_999_999, provider="test"))
        db.flush()
        asof = days[-1]
        f = compute_features(db, sec.id, asof)
        assert f.price is not None and f.price < 12
        assert f.ret_1d is not None and abs(f.ret_1d) < 0.05

    def test_retrospective_uses_only_post_signal_bars(self, db):
        """Gli outcome usano P0 = apertura della seduta successiva, non la
        chiusura già nota al momento del segnale."""
        from app.models import RiskScore
        from app.validation.retrospective import reference_price
        sec = _sec(db)
        days = business_days_back(date(2026, 6, 30), 10)
        for i, d in enumerate(days):
            db.add(MarketBar(security_id=sec.id, bar_date=d, session="regular",
                             open=10.0 + i, high=11.0 + i, low=9.0 + i, close=10.5 + i,
                             volume=1000, provider="test"))
        db.flush()
        score = RiskScore(security_id=sec.id, score_date=days[-2], confidence_grade="B",
                          state="MONITORARE", scoring_version="t", config_hash="t",
                          code_version="t")
        db.add(score)
        db.flush()
        ref = reference_price(db, score)
        assert ref is not None
        p0, ref_date = ref
        assert ref_date == days[-1]           # seduta successiva al segnale
        assert p0 == 10.0 + len(days) - 1     # apertura, non chiusura del giorno del segnale
