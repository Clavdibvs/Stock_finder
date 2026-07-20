"""Split, reverse split e blocco per azioni non riconciliate."""
from __future__ import annotations

from datetime import date

from app.candidates.features import compute_features
from app.models import CorporateAction, MarketBar, Security
from app.seed.demo import business_days_back


def _sec_with_bars(db, name: str, prices: list[float], volumes: list[float] | None = None):
    sec = Security(name=name, is_demo=True)
    db.add(sec)
    db.flush()
    days = business_days_back(date(2026, 6, 30), len(prices))
    for d, p, v in zip(days, prices, volumes or [100_000] * len(prices)):
        db.add(MarketBar(security_id=sec.id, bar_date=d, session="regular",
                         open=p, high=p * 1.01, low=p * 0.99, close=p,
                         volume=v, provider="test"))
    db.flush()
    return sec, days


class TestUnreconciledBlock:
    def test_unreconciled_action_blocks_security(self, db):
        """Corporate action non riconciliata -> titolo bloccato, nessuna feature."""
        sec, days = _sec_with_bars(db, "Blocked Corp", [10.0] * 80)
        db.add(CorporateAction(security_id=sec.id, action_type="reverse_split",
                               ratio=0.1, effective_date=days[-5], reconciled=False))
        db.flush()
        f = compute_features(db, sec.id, days[-1])
        assert f.blocked_unreconciled_action is True
        assert f.price is None
        assert "corporate_action_unreconciled" in f.missing

    def test_no_signal_when_blocked(self, db):
        """La pipeline sopprime il segnale e registra una data quality issue."""
        from app.models import DataQualityIssue
        from app.scoring.pipeline import run_for_security
        from sqlalchemy import select
        sec, days = _sec_with_bars(db, "Blocked2 Corp", [10.0] * 80)
        db.add(CorporateAction(security_id=sec.id, action_type="split",
                               ratio=2.0, effective_date=days[-3], reconciled=False))
        db.flush()
        score = run_for_security(db, sec, days[-1])
        assert score is None
        issue = db.scalar(select(DataQualityIssue).where(
            DataQualityIssue.security_id == sec.id))
        assert issue is not None
        assert issue.issue_type == "unreconciled_corporate_action"

    def test_reconciled_action_does_not_block(self, db):
        sec, days = _sec_with_bars(db, "OK Corp", [10.0] * 80)
        db.add(CorporateAction(security_id=sec.id, action_type="reverse_split",
                               ratio=0.1, effective_date=days[-5], reconciled=True))
        db.flush()
        f = compute_features(db, sec.id, days[-1])
        assert f.blocked_unreconciled_action is False
        assert f.price == 10.0


class TestSplitHandling:
    def test_adjusted_series_no_false_signal(self, db):
        """Reverse split riconciliato su serie ADJUSTED: nessun rendimento fantasma.

        Su una serie correttamente rettificata il prezzo è continuo: il
        rendimento giornaliero attraverso lo split resta ~0, quindi il
        candidate generator non si attiva.
        """
        from app.candidates.generator import evaluate
        prices = [10.0] * 80  # serie adjusted: continua attraverso lo split
        sec, days = _sec_with_bars(db, "Split Corp", prices)
        db.add(CorporateAction(security_id=sec.id, action_type="reverse_split",
                               ratio=0.1, effective_date=days[-10], reconciled=True))
        db.flush()
        f = compute_features(db, sec.id, days[-1])
        assert abs(f.ret_1d or 0) < 0.01
        decision = evaluate(f, days[-1])
        assert decision.is_candidate is False

    def test_unadjusted_jump_would_be_caught_by_reconciliation(self, db):
        """Una serie NON rettificata (salto 10x) è il caso che la riconciliazione
        deve bloccare: con l'azione non riconciliata il titolo non produce segnali."""
        prices = [1.0] * 70 + [10.0] * 10  # salto da reverse split non applicato
        sec, days = _sec_with_bars(db, "Unadjusted Corp", prices)
        db.add(CorporateAction(security_id=sec.id, action_type="reverse_split",
                               ratio=0.1, effective_date=days[-10], reconciled=False))
        db.flush()
        f = compute_features(db, sec.id, days[-1])
        assert f.blocked_unreconciled_action is True  # nessun falso +900%
