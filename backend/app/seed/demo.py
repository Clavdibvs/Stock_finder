"""Dataset seed dimostrativo.

REGOLE:
- tutti i dati sono FITTIZI o ricostruzioni storiche etichettate (is_demo=True);
- niente è presentato come aggiornato in tempo reale;
- generazione deterministica (random.Random con seed fisso);
- il seed carica dati grezzi (securities, barre, eventi, documenti, claim) e
  poi esegue la PIPELINE REALE (dedup, candidate generator, scoring, gate,
  retrospective) sugli stessi dati: la demo esercita il codice di produzione.

Casi coperti:
  ATAI  rumor M&A (ispirato al caso reale, ricostruito)  -> EVENTO BINARIO
  BIOP  biotech pre-readout PDUFA                        -> EVENTO BINARIO
  QNTC  meme/pivot quantum, short interest alto          -> POSSIBILE SQUEEZE
  MFLO  microcap sotto $1, promo                         -> NON QUANTIFICABILE
  PXLD  storia troppo corta, dati stale                  -> DATI INSUFFICIENTI
  NVTX  biotech post-readout debole                      -> RISCHIO ELEVATO
  HYGN  offering/diluizione (shelf+ATM)                  -> RISCHIO ELEVATO
  VMEM  meme, origine unica + 100 duplicati              -> RISCHIO ELEVATO
  SLRB  earnings surprise reale                          -> MONITORARE
  CRGX  rumor M&A smentito (storia + retrospettiva)      -> MONITORARE
  RVSP  reverse split non riconciliato                   -> bloccato (QC)
  DLST  delisted con outcome storico completo            -> storico
"""
from __future__ import annotations

import random
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.claims.graph import assign_duplicate_family
from app.core.audit import audit
from app.models import (
    AppSetting, Claim, ClaimRelation, CorporateAction, DataQualityIssue, Document,
    DocumentSource, Event, IngestionRun, MarketBar, Notification, RiskScore,
    Security, SecurityListing, WatchlistItem, utcnow,
)
from app.scoring.pipeline import run_for_security
from app.validation.retrospective import compute_outcomes, update_all_pending

SEED = 42
PROVIDER = "demo"


# ----------------------------------------------------------- date helpers ---

def business_days_back(end: date, n: int) -> list[date]:
    """Ultime n sedute (lun-ven) fino a `end` inclusa, in ordine cronologico."""
    days: list[date] = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


def last_business_day(today: date | None = None) -> date:
    d = today or date.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _ts(d: date, hour: int = 13, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour, minute), tzinfo=UTC)


# ------------------------------------------------------------- generatori ---

def gen_bars(rng: random.Random, days: list[date], start_price: float,
             base_vol: float, drift: float = 0.0,
             pattern: list[tuple[int, float, float]] | None = None) -> list[dict]:
    """Serie OHLCV deterministica. pattern = [(indice_da_fine, rendimento, mult_volume)]."""
    pattern = pattern or []
    special = {len(days) + idx if idx < 0 else idx: (ret, vmult) for idx, ret, vmult in pattern}
    bars = []
    price = start_price
    for i, d in enumerate(days):
        if i in special:
            ret, vmult = special[i]
        else:
            ret, vmult = rng.gauss(drift, 0.022), abs(rng.gauss(1.0, 0.25))
        open_p = price * (1 + rng.gauss(0, 0.004))
        close_p = price * (1 + ret)
        hi = max(open_p, close_p) * (1 + abs(rng.gauss(0, 0.008)))
        lo = min(open_p, close_p) * (1 - abs(rng.gauss(0, 0.008)))
        volume = base_vol * vmult
        bars.append({"bar_date": d, "open": round(open_p, 4), "high": round(hi, 4),
                     "low": round(lo, 4), "close": round(close_p, 4),
                     "volume": round(volume)})
        price = close_p
    return bars


def add_security(db: Session, ticker: str, name: str, sector: str,
                 shares: float | None, float_shares: float | None,
                 exchange: str = "NASDAQ", cik: str | None = None,
                 status: str = "active", sec_type: str = "common_stock",
                 listed_from: date | None = None) -> Security:
    sec = Security(name=name, sector=sector, cik=cik, is_demo=True, security_type=sec_type)
    db.add(sec)
    db.flush()
    db.add(SecurityListing(
        security_id=sec.id, ticker=ticker, exchange=exchange, status=status,
        valid_from=listed_from or date(2020, 1, 2),
        shares_outstanding=shares, float_shares=float_shares,
    ))
    db.flush()
    return sec


def add_bars(db: Session, sec: Security, bars: list[dict]) -> None:
    for b in bars:
        db.add(MarketBar(security_id=sec.id, session="regular", provider=PROVIDER,
                         adjusted=True, **b))


def add_doc(db: Session, sec: Security, source: DocumentSource, url: str, title: str,
            published: datetime | None, level: int, excerpt: str,
            publisher: str | None = None, author: str | None = None,
            first_seen: datetime | None = None,
            license_state: str = "excerpt_allowed") -> Document:
    doc = Document(
        security_id=sec.id, source_id=source.id, url_canonical=url, url_original=url,
        title=title, author=author, publisher=publisher or source.publisher,
        published_at=published, first_seen_at=first_seen or published or utcnow(),
        retrieved_at=first_seen or published or utcnow(),
        original_timezone="America/New_York", source_level=level,
        excerpt=excerpt, license_state=license_state,
    )
    db.add(doc)
    db.flush()
    assign_duplicate_family(db, doc)
    db.flush()
    return doc


# ------------------------------------------------------------------- seed ---

def seed_sources(db: Session) -> dict[str, DocumentSource]:
    registry = [
        ("SEC EDGAR", "sec.gov", "U.S. Securities and Exchange Commission", 1, "full_allowed",
         "Documenti pubblici federali; conservabili con fair access", True),
        ("Company IR", "example-ir.com", "Investor Relations (demo)", 2, "excerpt_allowed",
         "Comunicati societari: URL, metadata ed estratti", True),
        ("Reuters (demo)", "reuters.com", "Reuters", 3, "metadata_only",
         "Solo metadati e link; nessuna copia integrale", False),
        ("Newswire aggregato (demo)", "newswire-demo.com", "Aggregatori vari", 10, "metadata_only",
         "Riscritture automatiche: mai conteggiate come conferme", False),
        ("Finanza-blog (demo)", "finblog-demo.com", "Blog finanziario", 8, "metadata_only",
         "Opinioni non verificate", False),
        ("PromoWire (demo)", "promowire-demo.com", "Contenuti sponsorizzati", 9, "metadata_only",
         "Contenuto promozionale: possibile rischio", False),
        ("Forum retail (demo)", "forum-demo.com", "Community", 7, "metadata_only",
         "Post di utenti identificabili: segnale di attenzione", False),
        ("FDA / openFDA", "api.fda.gov", "U.S. Food and Drug Administration", 1, "full_allowed",
         "Fonte pubblica; mantenere provenienza e data", False),
        ("ClinicalTrials.gov", "clinicaltrials.gov", "NIH", 1, "full_allowed",
         "Registro trial; conservare submission e posting date", False),
        ("Nasdaq Halts", "nasdaqtrader.com", "Nasdaq", 1, "full_allowed",
         "Feed halt ufficiale", False),
    ]
    out = {}
    for name, domain, publisher, level, lic, notes, configured in registry:
        src = db.scalar(select(DocumentSource).where(DocumentSource.name == name))
        if src is None:
            src = DocumentSource(name=name, domain=domain, publisher=publisher,
                                 default_source_level=level, license_status=lic,
                                 notes=notes, configured=configured, enabled=True)
            db.add(src)
            db.flush()
        out[name] = src
    return out


def run_demo_seed(db: Session, asof: date | None = None) -> dict:
    """Esegue il seed completo. Idempotente: se i dati demo esistono, esce."""
    existing = db.scalar(select(Security).where(Security.is_demo.is_(True)).limit(1))
    if existing is not None:
        return {"status": "already_seeded"}

    rng = random.Random(SEED)
    asof = asof or last_business_day()
    days = business_days_back(asof, 180)
    run = IngestionRun(job_name="demo_seed", triggered_by="manual", status="running")
    db.add(run)
    db.flush()

    sources = seed_sources(db)
    sec_ir = sources["Company IR"]
    sec_edgar = sources["SEC EDGAR"]
    reuters = sources["Reuters (demo)"]
    newswire = sources["Newswire aggregato (demo)"]
    blog = sources["Finanza-blog (demo)"]
    promo = sources["PromoWire (demo)"]
    forum = sources["Forum retail (demo)"]

    # ---- benchmark (indice demo per outcome relativi) ----
    bench = add_security(db, "DBMK", "Indice benchmark (demo)", "Index",
                         None, None, sec_type="index")
    add_bars(db, bench, gen_bars(rng, days, 100.0, 1_000_000, drift=0.0004))

    # =====================================================================
    # ATAI — rumor M&A, ricostruzione demo del caso di luglio 2026
    # =====================================================================
    atai = add_security(db, "ATAI", "AtaiBeckley Inc. (demo ricostruito)", "Biotech",
                        180_000_000, 140_000_000, cik="0001840904")
    atai_bars = gen_bars(rng, days[:-1], 4.9, 7_700_000, drift=0.0005,
                         pattern=[(-3, -0.02, 1.1), (-2, -0.01, 1.2), (-1, -0.055, 1.4)])
    add_bars(db, atai, atai_bars)
    prev_close = atai_bars[-1]["close"]
    # seduta del gap: apre +58% dopo il rumor serale
    gap_open = round(prev_close * 1.58, 4)
    db.add(MarketBar(security_id=atai.id, bar_date=asof, session="regular",
                     provider=PROVIDER, open=gap_open, high=round(gap_open * 1.06, 4),
                     low=round(gap_open * 0.93, 4), close=round(prev_close * 1.62, 4),
                     volume=41_000_000, adjusted=True))
    db.add(MarketBar(security_id=atai.id, bar_date=asof, session="premarket",
                     provider=PROVIDER, open=round(prev_close * 1.35, 4),
                     high=round(prev_close * 1.68, 4), low=round(prev_close * 1.3, 4),
                     close=round(prev_close * 1.617, 4), volume=4_100_000, adjusted=True))

    ev_rumor = Event(
        security_id=atai.id, event_type="ma_rumor", status="pending", is_binary=True,
        materiality="high",
        title="Rumor: grande pharma in trattative per acquisire la società (fonti anonime)",
        announced_at=_ts(asof - timedelta(days=1), 21, 45),
        classified_by="rule",
        details={"note": "Claim centrale non confermato; nessun 8-K alla verifica"},
    )
    db.add(ev_rumor)
    db.flush()

    d_origin = add_doc(
        db, atai, reuters,
        "https://reuters-demo.com/atai-ma-talks?utm_source=feed",
        "Esclusiva: colloqui avanzati per l'acquisizione del produttore di psichedelici",
        _ts(asof - timedelta(days=1), 21, 40), 6,
        "Secondo persone informate sui fatti, le trattative sarebbero in fase avanzata; "
        "un annuncio potrebbe arrivare entro la settimana. Le società non hanno commentato.",
        author="Reuters staff (demo)", license_state="metadata_only",
    )
    # 12 riscritture della stessa origine: UNA famiglia, UNA origine informativa
    for i in range(12):
        add_doc(
            db, atai, newswire,
            f"https://newswire-demo.com/rewrite-atai-{i}?utm_campaign=x&gclid=abc{i}",
            "Esclusiva: colloqui avanzati per l'acquisizione del produttore di psichedelici",
            _ts(asof - timedelta(days=1), 22, 5 + i), 10,
            "Secondo persone informate sui fatti, le trattative sarebbero in fase avanzata; "
            "un annuncio potrebbe arrivare entro la settimana. Le società non hanno commentato.",
            license_state="metadata_only",
        )
    d_f4 = add_doc(
        db, atai, sec_edgar,
        "https://sec.gov/Archives/edgar/data/1840904/form4-demo.html",
        "Form 4 — variazione proprietà insider (demo)",
        _ts(asof - timedelta(days=7), 18, 0), 1,
        "Registra variazioni nella proprietà beneficiaria di un insider. Non conferma né "
        "smentisce alcuna transazione societaria.",
    )
    c_rumor = Claim(
        security_id=atai.id, subject="Grande società farmaceutica",
        predicate="sarebbe in trattative per acquisire", object="la società",
        claim_date=asof - timedelta(days=1), status="rumor", confirmation_level=6,
        evidence_span="le trattative sarebbero in fase avanzata; un annuncio potrebbe "
                      "arrivare entro la settimana",
        source_document_id=d_origin.id, extracted_by="rule",
    )
    c_noconf = Claim(
        security_id=atai.id, subject="La società", predicate="non ha depositato",
        object="alcun 8-K relativo a una transazione M&A", claim_date=asof,
        status="fatto", confirmation_level=1,
        evidence_span="Nessun 8-K risulta depositato alla data di verifica (assenza di "
                      "conferma, NON smentita).",
        source_document_id=d_f4.id, extracted_by="manual",
    )
    db.add_all([c_rumor, c_noconf])
    db.flush()
    db.add(ClaimRelation(claim_id=c_noconf.id, related_claim_id=c_rumor.id,
                         relation="contraddice",
                         note="Assenza di conferma nei canali ufficiali al momento del controllo"))

    # =====================================================================
    # BIOP — biotech pre-readout: PDUFA imminente
    # =====================================================================
    biop = add_security(db, "BIOP", "BioPeak Sciences (demo)", "Biotech",
                        45_000_000, 38_000_000)
    add_bars(db, biop, gen_bars(rng, days, 8.2, 900_000, drift=0.004,
                                pattern=[(-2, 0.09, 2.6), (-1, 0.12, 3.4)]))
    db.add(Event(
        security_id=biop.id, event_type="fda_decision_pending", status="pending",
        is_binary=True, materiality="high",
        title="Decisione FDA (PDUFA) attesa entro 10 giorni sul farmaco principale",
        announced_at=_ts(asof - timedelta(days=12), 13, 0),
        details={"pdufa_date": (asof + timedelta(days=8)).isoformat()},
    ))
    d_biop = add_doc(
        db, biop, sec_ir, "https://example-ir.com/biop/pdufa-reminder",
        "La società ricorda la data PDUFA imminente per il proprio candidato principale",
        _ts(asof - timedelta(days=12), 13, 0), 2,
        "La decisione dell'autorità è attesa entro il trimestre. L'esito è binario: "
        "approvazione o Complete Response Letter.",
    )
    db.add(Claim(
        security_id=biop.id, subject="FDA", predicate="deciderà entro 10 giorni su",
        object="il candidato principale della società", claim_date=asof,
        status="fatto", confirmation_level=2,
        evidence_span="La decisione dell'autorità è attesa entro il trimestre.",
        source_document_id=d_biop.id, extracted_by="rule",
    ))

    # =====================================================================
    # QNTC — pivot quantum + meme, short interest alto -> squeeze gate
    # =====================================================================
    qntc = add_security(db, "QNTC", "QuantumCortex AI (demo)", "Technology",
                        60_000_000, 22_000_000)
    # short interest ufficiale noto (FINRA demo): 34% del float
    qntc_listing = db.scalar(
        select(SecurityListing).where(SecurityListing.security_id == qntc.id)
    )
    qntc_listing.short_interest_shares = 7_480_000
    qntc_listing.short_interest_date = asof - timedelta(days=9)
    add_bars(db, qntc, gen_bars(rng, days, 3.1, 2_500_000, drift=0.006,
                                pattern=[(-3, 0.18, 5.0), (-2, 0.22, 8.0), (-1, 0.16, 9.5)]))
    db.add(Event(
        security_id=qntc.id, event_type="meme_attention", status="occurred", is_binary=False,
        materiality="high", title="Attenzione retail concentrata dopo pivot quantum computing",
        announced_at=_ts(asof - timedelta(days=3), 15, 0),
    ))
    d_qf = add_doc(
        db, qntc, forum, "https://forum-demo.com/qntc-thread-1",
        "QNTC: il prossimo 10x? Lo short interest è enorme",
        _ts(asof - timedelta(days=2), 16, 0), 7,
        "Thread con alta concentrazione di autori; molti repost, pochi contenuti originali.",
        license_state="metadata_only",
    )
    db.add(Claim(
        security_id=qntc.id, subject="La società", predicate="ha annunciato un pivot verso",
        object="il quantum computing", claim_date=asof - timedelta(days=3),
        status="interpretazione", confirmation_level=7,
        evidence_span="Thread con alta concentrazione di autori; molti repost.",
        source_document_id=d_qf.id, extracted_by="rule",
    ))
    # =====================================================================
    # MFLO — microcap sotto $1 con promo -> non quantificabile
    # =====================================================================
    mflo = add_security(db, "MFLO", "MicroFlow Devices (demo)", "Industrials",
                        30_000_000, 9_000_000, exchange="NYSE American")
    add_bars(db, mflo, gen_bars(rng, days, 0.45, 300_000, drift=0.003,
                                pattern=[(-2, 0.25, 6.0), (-1, 0.31, 8.0)]))
    db.add(Event(
        security_id=mflo.id, event_type="promotion_suspected", status="occurred",
        is_binary=False, materiality="high",
        title="Campagna promozionale sospetta su micro-cap illiquida",
        announced_at=_ts(asof - timedelta(days=2), 14, 0),
    ))
    add_doc(
        db, mflo, promo, "https://promowire-demo.com/mflo-next-big-thing",
        "MFLO: la prossima rivoluzione industriale (contenuto sponsorizzato)",
        _ts(asof - timedelta(days=2), 14, 0), 9,
        "Contenuto sponsorizzato con price target privi di fonte.",
        license_state="metadata_only",
    )

    # =====================================================================
    # PXLD — dati insufficienti (storia corta + stale)
    # =====================================================================
    pxld = add_security(db, "PXLD", "Pixeland Media (demo)", "Media",
                        25_000_000, 20_000_000, listed_from=asof - timedelta(days=60))
    short_days = business_days_back(asof - timedelta(days=7), 30)
    add_bars(db, pxld, gen_bars(rng, short_days, 5.5, 400_000, drift=0.01,
                                pattern=[(-1, 0.21, 4.0)]))
    db.add(DataQualityIssue(
        run_id=run.id, security_id=pxld.id, issue_type="stale_source", severity="warn",
        message="Ultima barra più vecchia di 3 sedute: fonte demo interrotta (esempio).",
    ))

    # =====================================================================
    # NVTX — biotech post-readout debole -> rischio elevato
    # =====================================================================
    nvtx = add_security(db, "NVTX", "Nuvexa Therapeutics (demo)", "Biotech",
                        52_000_000, 47_000_000)
    add_bars(db, nvtx, gen_bars(rng, days, 6.0, 1_100_000, drift=0.001,
                                pattern=[(-2, 0.38, 9.0), (-1, 0.12, 8.0)]))
    ev_nvtx = Event(
        security_id=nvtx.id, event_type="clinical_readout_positive", status="occurred",
        is_binary=False, materiality="high",
        title="Topline Phase 2a: endpoint primario di sicurezza raggiunto; efficacia esplorativa",
        announced_at=_ts(days[-2], 11, 30),
    )
    db.add(ev_nvtx)
    d_nv_ir = add_doc(
        db, nvtx, sec_ir, "https://example-ir.com/nvtx/topline-2a",
        "Nuvexa annuncia risultati topline positivi dello studio esplorativo Phase 2a",
        _ts(days[-2], 11, 30), 2,
        "Endpoint primario di sicurezza raggiunto in 71 pazienti. Un risultato esplorativo "
        "di efficacia riporta p=0,036 a una coda; lo studio non era dimensionato per "
        "dimostrare efficacia statistica.",
    )
    d_nv_blog = add_doc(
        db, nvtx, blog, "https://finblog-demo.com/nvtx-breakthrough",
        "Nuvexa: risultati rivoluzionari, il titolo può triplicare",
        _ts(days[-1], 15, 0), 8,
        "L'articolo definisce i risultati 'rivoluzionari' senza discutere il "
        "dimensionamento statistico dello studio.",
        license_state="metadata_only",
    )
    for i in range(4):
        add_doc(
            db, nvtx, newswire,
            f"https://newswire-demo.com/nvtx-echo-{i}?utm_source=agg",
            "Nuvexa: risultati rivoluzionari, il titolo può triplicare",
            _ts(asof, 9 + i, 15), 10,
            "L'articolo definisce i risultati 'rivoluzionari' senza discutere il "
            "dimensionamento statistico dello studio.",
            license_state="metadata_only",
        )
    c_nv_fact = Claim(
        security_id=nvtx.id, subject="Lo studio Phase 2a", predicate="ha raggiunto",
        object="l'endpoint primario di sicurezza", figure="71 pazienti",
        claim_date=days[-2], status="fatto", confirmation_level=2,
        evidence_span="Endpoint primario di sicurezza raggiunto in 71 pazienti.",
        source_document_id=d_nv_ir.id, extracted_by="rule",
    )
    c_nv_op = Claim(
        security_id=nvtx.id, subject="I risultati", predicate="sarebbero",
        object="rivoluzionari e il titolo può triplicare",
        claim_date=days[-1], status="opinione", confirmation_level=8,
        evidence_span="L'articolo definisce i risultati 'rivoluzionari'.",
        source_document_id=d_nv_blog.id, extracted_by="rule",
    )
    c_nv_stat = Claim(
        security_id=nvtx.id, subject="Lo studio", predicate="non era dimensionato per",
        object="dimostrare efficacia statistica", figure="p=0,036 a una coda",
        claim_date=days[-2], status="fatto", confirmation_level=2,
        evidence_span="lo studio non era dimensionato per dimostrare efficacia statistica.",
        source_document_id=d_nv_ir.id, extracted_by="rule",
    )
    db.add_all([c_nv_fact, c_nv_op, c_nv_stat])
    db.flush()
    db.add(ClaimRelation(claim_id=c_nv_stat.id, related_claim_id=c_nv_op.id,
                         relation="contraddice",
                         note="Headline positiva vs forza probatoria del contenuto"))
    db.add(ClaimRelation(claim_id=c_nv_op.id, related_claim_id=c_nv_fact.id,
                         relation="deriva_da"))

    # =====================================================================
    # HYGN — offering/diluizione con shelf aperto -> rischio elevato
    # =====================================================================
    hygn = add_security(db, "HYGN", "HydroGenetix Energy (demo)", "Energy",
                        80_000_000, 65_000_000)
    add_bars(db, hygn, gen_bars(rng, days, 2.8, 1_800_000, drift=0.012,
                                pattern=[(-2, 0.14, 3.2), (-1, 0.17, 4.1)]))
    db.add(Event(
        security_id=hygn.id, event_type="offering_or_dilution", status="occurred",
        is_binary=False, materiality="high",
        title="Prospectus supplement 424B5: programma ATM da $150M su shelf S-3",
        announced_at=_ts(days[-2], 21, 30),
        details={"shelf_open": True, "atm_capacity_usd": 150_000_000},
    ))
    d_hy = add_doc(
        db, hygn, sec_edgar, "https://sec.gov/Archives/edgar/data/999001/424b5-demo.html",
        "424B5 — Prospectus supplement: at-the-market offering program (demo)",
        _ts(days[-2], 21, 30), 1,
        "Programma ATM fino a $150 milioni ai sensi della shelf S-3 esistente. La shelf "
        "descrive capacità potenziale: non dimostra vendite già avvenute.",
    )
    add_doc(
        db, hygn, newswire, "https://newswire-demo.com/hygn-atm-echo?ref=agg",
        "424B5 — Prospectus supplement: at-the-market offering program (demo)",
        _ts(asof, 9, 5), 10,
        "Programma ATM fino a $150 milioni ai sensi della shelf S-3 esistente. La shelf "
        "descrive capacità potenziale: non dimostra vendite già avvenute.",
        license_state="metadata_only",
    )
    db.add(Claim(
        security_id=hygn.id, subject="La società", predicate="ha attivato",
        object="un programma ATM su shelf S-3", figure="$150M",
        claim_date=days[-2], status="fatto", confirmation_level=1,
        evidence_span="Programma ATM fino a $150 milioni ai sensi della shelf S-3 esistente.",
        source_document_id=d_hy.id, extracted_by="rule",
    ))

    # =====================================================================
    # VMEM — meme: origine unica, 100 duplicati -> una famiglia
    # =====================================================================
    vmem = add_security(db, "VMEM", "VitaMem Labs (demo)", "Healthcare",
                        35_000_000, 15_000_000)
    add_bars(db, vmem, gen_bars(rng, days, 1.9, 2_000_000, drift=0.02,
                                pattern=[(-3, 0.15, 4.0), (-2, 0.19, 6.0), (-1, 0.24, 7.5)]))
    db.add(Event(
        security_id=vmem.id, event_type="meme_attention", status="occurred", is_binary=False,
        materiality="high", title="Rally guidato da attenzione social senza notizia fondamentale",
        announced_at=_ts(days[-3], 14, 0),
    ))
    d_vm_origin = add_doc(
        db, vmem, forum, "https://forum-demo.com/vmem-original-post",
        "VMEM sta per esplodere: ecco perché (post originale)",
        _ts(asof, 12, 55), 7,
        "Post originale di un utente identificabile; nessuna fonte primaria citata; "
        "price target privo di fonte.",
        license_state="metadata_only",
    )
    for i in range(100):
        add_doc(
            db, vmem, newswire,
            f"https://newswire-demo.com/vmem-copy-{i}?utm_medium=social&fbclid=z{i}",
            "VMEM sta per esplodere: ecco perché (post originale)",
            _ts(asof, 13, (i % 50) + 1), 10,
            "Post originale di un utente identificabile; nessuna fonte primaria citata; "
            "price target privo di fonte.",
            license_state="metadata_only",
        )
    db.add(Claim(
        security_id=vmem.id, subject="Il titolo", predicate="starebbe per",
        object="esplodere al rialzo", claim_date=asof,
        status="previsione", confirmation_level=7,
        evidence_span="price target privo di fonte.",
        source_document_id=d_vm_origin.id, extracted_by="rule",
    ))

    # =====================================================================
    # SLRB — earnings surprise con fonte primaria -> monitorare
    # =====================================================================
    slrb = add_security(db, "SLRB", "SolarBridge Systems (demo)", "Energy",
                        120_000_000, 100_000_000, exchange="NYSE")
    add_bars(db, slrb, gen_bars(rng, days, 14.0, 3_000_000, drift=0.002,
                                pattern=[(-2, 0.19, 4.0), (-1, 0.07, 2.4)]))
    db.add(Event(
        security_id=slrb.id, event_type="earnings_surprise", status="occurred",
        is_binary=False, materiality="high",
        title="Ricavi trimestrali +40% oltre le stime; guidance alzata",
        announced_at=_ts(days[-2], 11, 0),
    ))
    d_sl = add_doc(
        db, slrb, sec_edgar, "https://sec.gov/Archives/edgar/data/888002/10q-demo.html",
        "10-Q — risultati del trimestre (demo)",
        _ts(days[-2], 11, 0), 1,
        "Ricavi in crescita del 40% oltre il consenso; margini in miglioramento; "
        "guidance annuale rivista al rialzo.",
    )
    db.add(Claim(
        security_id=slrb.id, subject="I ricavi trimestrali", predicate="sono cresciuti del",
        object="40% oltre il consenso", figure="+40%",
        claim_date=days[-2], status="fatto", confirmation_level=1,
        evidence_span="Ricavi in crescita del 40% oltre il consenso.",
        source_document_id=d_sl.id, extracted_by="rule",
    ))

    # =====================================================================
    # CRGX — rumor M&A smentito, con storia di score e retrospettiva
    # =====================================================================
    crgx = add_security(db, "CRGX", "CargoLinx Logistics (demo)", "Industrials",
                        90_000_000, 75_000_000, exchange="NYSE")
    # rally 15 sedute fa su rumor, poi smentita e discesa
    crgx_pattern = [(-16, 0.22, 5.0), (-15, 0.07, 3.0), (-13, -0.12, 4.0),
                    (-12, -0.06, 2.5), (-8, -0.04, 1.5), (-1, 0.16, 2.4)]
    add_bars(db, crgx, gen_bars(rng, days, 22.0, 1_500_000, drift=0.0,
                                pattern=crgx_pattern))
    ev_cr_rumor = Event(
        security_id=crgx.id, event_type="ma_rumor_denied", status="resolved_negative",
        is_binary=True, materiality="high",
        title="Rumor di acquisizione smentito ufficialmente dalla società",
        announced_at=_ts(days[-13], 12, 0),
    )
    db.add(ev_cr_rumor)
    d_cr_rumor = add_doc(
        db, crgx, blog, "https://finblog-demo.com/crgx-buyout-chatter",
        "Voci di acquisizione su CargoLinx: fonti non specificate",
        _ts(days[-16], 15, 30), 6,
        "Voci di un'offerta a premio; nessuna fonte identificata.",
        license_state="metadata_only",
    )
    d_cr_denial = add_doc(
        db, crgx, sec_ir, "https://example-ir.com/crgx/statement",
        "CargoLinx: nessuna trattativa in corso",
        _ts(days[-13], 12, 0), 2,
        "La società dichiara di non essere in trattative per una vendita.",
    )
    c_cr_rumor = Claim(
        security_id=crgx.id, subject="Un acquirente non identificato",
        predicate="avrebbe offerto un premio per", object="la società",
        claim_date=days[-16], status="rumor", confirmation_level=6,
        evidence_span="Voci di un'offerta a premio; nessuna fonte identificata.",
        source_document_id=d_cr_rumor.id, extracted_by="rule",
    )
    c_cr_denial = Claim(
        security_id=crgx.id, subject="La società", predicate="ha smentito",
        object="qualsiasi trattativa di vendita", claim_date=days[-13],
        status="fatto", confirmation_level=2,
        evidence_span="La società dichiara di non essere in trattative per una vendita.",
        source_document_id=d_cr_denial.id, extracted_by="rule",
    )
    db.add_all([c_cr_rumor, c_cr_denial])
    db.flush()
    db.add(ClaimRelation(claim_id=c_cr_denial.id, related_claim_id=c_cr_rumor.id,
                         relation="contraddice", note="Smentita ufficiale del rumor"))

    # =====================================================================
    # RVSP — reverse split NON riconciliato -> blocco QC (nessun segnale)
    # =====================================================================
    rvsp = add_security(db, "RVSP", "RevoSpark Motors (demo)", "Automotive",
                        12_000_000, 8_000_000)
    add_bars(db, rvsp, gen_bars(rng, days, 9.0, 700_000, drift=0.001,
                                pattern=[(-1, 0.19, 3.0)]))
    db.add(CorporateAction(
        security_id=rvsp.id, action_type="reverse_split", ratio=0.1,
        effective_date=days[-5], reconciled=False,
        details={"nota": "Reverse split 1:10 in attesa di riconciliazione barre"},
    ))

    # =====================================================================
    # DLST — delisted con outcome storico completo
    # =====================================================================
    dlst = add_security(db, "DLST", "Delistra Corp (demo)", "Consumer",
                        40_000_000, 30_000_000, status="delisted")
    # storia fino a 30 sedute fa: rally poi crollo -35%
    dlst_days = days[:150]
    dlst_pattern = [(-31, 0.28, 6.0), (-30, 0.11, 4.0), (-27, -0.18, 5.0),
                    (-25, -0.15, 4.0), (-22, -0.10, 3.0)]
    add_bars(db, dlst, gen_bars(rng, dlst_days, 12.0, 900_000, drift=-0.002,
                                pattern=dlst_pattern))
    db.add(CorporateAction(
        security_id=dlst.id, action_type="delisting", effective_date=dlst_days[-1],
        reconciled=True, details={"nota": "Delisting completato (demo)"},
    ))

    db.flush()

    # ------------------------------------------------------------------
    # ESECUZIONE PIPELINE REALE sul dataset demo
    # ------------------------------------------------------------------
    demo_secs = db.scalars(
        select(Security).where(Security.is_demo.is_(True),
                               Security.security_type == "common_stock")
    ).all()

    # score storici per CRGX (giorno del rumor) e DLST (giorno del rally)
    hist_targets = [
        (crgx, days[-16]), (crgx, days[-15]),
        (dlst, dlst_days[-31]),
        (vmem, days[-3]),
    ]
    for sec, hist_date in hist_targets:
        run_for_security(db, sec, hist_date, run_id=run.id)

    # ranking odierno
    for sec in demo_secs:
        run_for_security(db, sec, asof, run_id=run.id)

    # retrospettive per gli score storici
    for score in db.scalars(select(RiskScore).where(RiskScore.score_date < asof)):
        compute_outcomes(db, score)
    update_all_pending(db)

    # ------------------------------------------------------------------
    # watchlist, notifiche, issue dimostrative
    # ------------------------------------------------------------------
    db.add(WatchlistItem(security_id=nvtx.id,
                         note="Demo: verificare la lettura completa dei dati Phase 2a."))
    db.add(WatchlistItem(security_id=atai.id,
                         note="Demo: attendere 8-K o smentita; NON operare su rumor."))
    db.add(WatchlistItem(security_id=slrb.id,
                         note="Demo: rally con catalizzatore fondamentale primario — "
                              "resta sotto soglia nella lista primaria."))
    db.add(WatchlistItem(security_id=crgx.id,
                         note="Demo: rumor smentito con storico score e retrospettiva."))
    db.add_all([
        Notification(security_id=atai.id, rule="new_in_top10",
                     title="ATAI (demo): nuovo candidato — EVENTO BINARIO",
                     body="Gap pre-market ~+60% su rumor M&A non confermato. Stato: evitare.",
                     dedup_key=f"demo-atai-{asof}"),
        Notification(security_id=hygn.id, rule="dilution_filing",
                     title="HYGN (demo): filing di diluizione",
                     body="424B5: programma ATM da $150M su shelf S-3.",
                     dedup_key=f"demo-hygn-{asof}"),
        Notification(security_id=crgx.id, rule="rumor_resolved",
                     title="CRGX (demo): rumor smentito",
                     body="La società ha smentito ufficialmente le voci di acquisizione.",
                     dedup_key=f"demo-crgx-{days[-13]}"),
    ])
    db.add(DataQualityIssue(
        run_id=run.id, security_id=rvsp.id,
        issue_type="unreconciled_corporate_action", severity="error",
        message="RVSP (demo): reverse split 1:10 non riconciliato — titolo bloccato, nessun segnale.",
    ))
    db.add(DataQualityIssue(
        run_id=run.id, issue_type="provider_not_configured", severity="info",
        message="Modalità demo attiva: i provider live (market data, FDA, ClinicalTrials, "
                "halt, FINRA, discovery) risultano non configurati.",
    ))
    db.add(AppSetting(key="demo_seeded_at", value={"asof": asof.isoformat()}))

    run.status = "success"
    run.finished_at = utcnow()
    run.items_processed = len(demo_secs)
    audit(db, actor="system", action="demo_seed",
          details={"asof": asof.isoformat(), "securities": len(demo_secs)})
    db.commit()
    return {"status": "seeded", "asof": asof.isoformat(), "securities": len(demo_secs)}
