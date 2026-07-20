"""Adapter demo: legge i dati seed dal database, non chiama nessuna rete.

Completamente funzionante: alimenta tutte le schermate in modalità demo.
I dati sono chiaramente etichettati come dimostrativi (Security.is_demo).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import (
    AdapterStatus, Bar, CorporateActionData, MarketDataAdapter, NewsMetadata, ReferenceData,
)
from app.models import CorporateAction, Document, MarketBar, Security, SecurityListing


class DemoMarketDataAdapter(MarketDataAdapter):
    name = "demo"

    def __init__(self, db: Session):
        self.db = db

    def status(self) -> AdapterStatus:
        has_data = self.db.scalar(select(Security.id).where(Security.is_demo.is_(True)).limit(1))
        return AdapterStatus.OK if has_data else AdapterStatus.ERROR

    def _security(self, ticker: str) -> Security | None:
        listing = self.db.scalar(
            select(SecurityListing).where(SecurityListing.ticker == ticker).limit(1)
        )
        return self.db.get(Security, listing.security_id) if listing else None

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[Bar]:
        sec = self._security(ticker)
        if sec is None:
            return []
        rows = self.db.scalars(
            select(MarketBar).where(
                MarketBar.security_id == sec.id,
                MarketBar.bar_date >= start, MarketBar.bar_date <= end,
                MarketBar.session == "regular",
            ).order_by(MarketBar.bar_date)
        ).all()
        return [Bar(r.bar_date, r.session, r.open, r.high, r.low, r.close, r.volume, r.vwap)
                for r in rows]

    def get_intraday_bars(self, ticker: str, day: date) -> list[Bar]:
        sec = self._security(ticker)
        if sec is None:
            return []
        rows = self.db.scalars(
            select(MarketBar).where(
                MarketBar.security_id == sec.id,
                MarketBar.bar_date == day,
                MarketBar.session != "regular",
            )
        ).all()
        return [Bar(r.bar_date, r.session, r.open, r.high, r.low, r.close, r.volume, r.vwap)
                for r in rows]

    def get_reference_data(self, ticker: str) -> ReferenceData | None:
        sec = self._security(ticker)
        if sec is None:
            return None
        listing = self.db.scalar(
            select(SecurityListing).where(SecurityListing.security_id == sec.id)
            .order_by(SecurityListing.valid_from.desc()).limit(1)
        )
        return ReferenceData(
            ticker=ticker, name=sec.name, exchange=listing.exchange if listing else None,
            cik=sec.cik, sector=sec.sector,
            shares_outstanding=listing.shares_outstanding if listing else None,
            float_shares=listing.float_shares if listing else None,
        )

    def get_corporate_actions(self, ticker: str, start: date, end: date) -> list[CorporateActionData]:
        sec = self._security(ticker)
        if sec is None:
            return []
        rows = self.db.scalars(
            select(CorporateAction).where(
                CorporateAction.security_id == sec.id,
                CorporateAction.effective_date >= start,
                CorporateAction.effective_date <= end,
            )
        ).all()
        return [CorporateActionData(r.action_type, r.effective_date, r.ratio, r.details or {})
                for r in rows]

    def get_delisted(self) -> list[ReferenceData]:
        rows = self.db.scalars(
            select(SecurityListing).where(SecurityListing.status == "delisted")
        ).all()
        out = []
        for listing in rows:
            sec = self.db.get(Security, listing.security_id)
            if sec:
                out.append(ReferenceData(ticker=listing.ticker, name=sec.name,
                                         exchange=listing.exchange, cik=sec.cik))
        return out

    def get_news_metadata(self, ticker: str, start: date, end: date) -> list[NewsMetadata]:
        sec = self._security(ticker)
        if sec is None:
            return []
        rows = self.db.scalars(
            select(Document).where(Document.security_id == sec.id)
        ).all()
        return [NewsMetadata(
            url=d.url_canonical, title=d.title, published_at=d.published_at,
            publisher=d.publisher, author=d.author, excerpt=d.excerpt,
            source_level=d.source_level,
        ) for d in rows]
