"""Motore deterministico del Risk Index.

RiskIndex = 0.20R + 0.15V + 0.10A + 0.20C + 0.15D + 0.10F + 0.10B
(pesi in config/scoring.yaml, versionati)

Regole non negoziabili:
- stesso input + stessa versione => stesso output (nessuna componente casuale);
- un componente mancante NON vale zero: i pesi vengono rinormalizzati sui
  componenti disponibili e la confidence scende;
- i gate prevalgono sempre sullo score numerico;
- il Risk Index è un indice ORDINALE, mai una probabilità.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.candidates.features import Features
from app.claims.graph import NarrativeStats
from app.config import APP_VERSION, config_hash, scoring_config
from app.constants import (
    BINARY_EVENT_TYPES,
    STATE_BELOW_THRESHOLD,
    STATE_BINARY_EVENT,
    STATE_ELEVATED,
    STATE_INSUFFICIENT_DATA,
    STATE_MONITOR,
    STATE_POSSIBLE_SQUEEZE,
    STATE_UNQUANTIFIABLE,
)


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def scale(value: float, lo: float, hi: float) -> float:
    """Mappa lineare value in [lo, hi] -> [0, 100], con clamp."""
    if hi == lo:
        return 50.0
    return clamp((value - lo) / (hi - lo) * 100.0)


def combine(parts: list[float]) -> float | None:
    """Aggregazione dei fattori di un componente: 0.6·max + 0.4·media.

    Il massimo pesa di più della media: un singolo segnale estremo non deve
    essere diluito dai fattori normali. Deterministico e documentato in
    SCORING.md; da contestare in validazione come i pesi.
    """
    if not parts:
        return None
    return 0.6 * max(parts) + 0.4 * (sum(parts) / len(parts))


@dataclass
class EventContext:
    """Riassunto degli eventi rilevanti per il gate binario e i componenti."""
    pending_binary_types: list[str] = field(default_factory=list)
    has_pending_binary: bool = False
    dominant_event_type: str | None = None
    recent_dilution_filing: bool = False
    shelf_or_atm_open: bool = False
    has_fundamental_catalyst: bool = False   # earnings/guidance a supporto del rally
    recent_halt: bool = False


@dataclass
class ComponentScore:
    component: str
    value: float | None            # 0-100, None = non calcolabile
    weight: float
    factors: list[dict] = field(default_factory=list)

    @property
    def missing(self) -> bool:
        return self.value is None


@dataclass
class ScoreResult:
    risk_index: float | None
    components: dict[str, ComponentScore]
    squeeze_hazard: float | None
    squeeze_unknown: bool
    execution_hazard: float | None
    dilution_risk: float | None
    confidence_grade: str
    state: str
    gate_applied: str | None
    missing_data: list[str]
    invalidation_conditions: list[str]
    scoring_version: str
    config_hash: str
    code_version: str

    def all_factors(self) -> list[dict]:
        out = []
        for comp in self.components.values():
            out.extend(comp.factors)
        return out


# ------------------------------------------------------------- componenti ---

def component_R(f: Features) -> ComponentScore:
    """Rally extremity."""
    cfg = scoring_config()
    factors, parts = [], []
    if f.ret_1d is not None:
        s = scale(f.ret_1d, 0.0, 0.25)
        parts.append(s)
        factors.append({"component": "R", "name": "Rendimento 1 giorno", "direction": 1 if s > 50 else 0,
                        "value": round(s, 1), "explanation": f"Rendimento 1g {f.ret_1d:+.1%}"})
    if f.ret_5d is not None:
        s = scale(f.ret_5d, 0.0, 0.40)
        parts.append(s)
        factors.append({"component": "R", "name": "Rendimento 5 giorni", "direction": 1 if s > 50 else 0,
                        "value": round(s, 1), "explanation": f"Rendimento 5g {f.ret_5d:+.1%}"})
    if f.ret_20d is not None:
        s = scale(f.ret_20d, 0.0, 0.80)
        parts.append(s)
        factors.append({"component": "R", "name": "Rendimento 20 giorni", "direction": 1 if s > 50 else 0,
                        "value": round(s, 1), "explanation": f"Rendimento 20g {f.ret_20d:+.1%}"})
    if f.gap is not None:
        s = scale(f.gap, 0.0, 0.25)
        parts.append(s)
        factors.append({"component": "R", "name": "Gap di apertura", "direction": 1 if s > 50 else 0,
                        "value": round(s, 1), "explanation": f"Gap {f.gap:+.1%}"})
    if f.robust_z_ret is not None:
        s = scale(f.robust_z_ret, 0.0, 5.0)
        parts.append(s)
        factors.append({"component": "R", "name": "Robust-z del rendimento", "direction": 1 if s > 50 else 0,
                        "value": round(s, 1), "explanation": f"Robust-z {f.robust_z_ret:.1f}"})
    if f.dist_ema20_atr is not None:
        s = scale(f.dist_ema20_atr, 0.0, 4.0)
        parts.append(s)
        factors.append({"component": "R", "name": "Distanza da EMA20 in ATR", "direction": 1 if s > 50 else 0,
                        "value": round(s, 1), "explanation": f"{f.dist_ema20_atr:.1f} ATR sopra EMA20"})
    value = combine(parts)
    return ComponentScore("R", value, cfg["weights"]["R"], factors)


def component_V(f: Features) -> ComponentScore:
    cfg = scoring_config()
    factors, parts = [], []
    if f.rvol is not None:
        s = scale(f.rvol, 1.0, 5.0)
        parts.append(s)
        factors.append({"component": "V", "name": "Volume relativo", "direction": 1 if s > 50 else 0,
                        "value": round(s, 1), "explanation": f"RVOL {f.rvol:.1f}×"})
    if f.turnover_float is not None:
        s = scale(f.turnover_float, 0.0, 0.40)
        parts.append(s)
        factors.append({"component": "V", "name": "Turnover sul flottante", "direction": 1 if s > 50 else 0,
                        "value": round(s, 1), "explanation": f"Turnover {f.turnover_float:.0%} del float"})
    value = combine(parts)
    return ComponentScore("V", value, cfg["weights"]["V"], factors)


def component_A(f: Features) -> ComponentScore:
    cfg = scoring_config()
    factors, parts = [], []
    if f.attention_z is not None:
        s = scale(f.attention_z, 0.0, 5.0)
        parts.append(s)
        factors.append({"component": "A", "name": "Attenzione anomala", "direction": 1 if s > 50 else 0,
                        "value": round(s, 1), "explanation": f"Robust-z citazioni {f.attention_z:.1f}"})
    if f.attention_docs_1d is not None:
        s = scale(float(f.attention_docs_1d), 0.0, 15.0)
        parts.append(s)
        factors.append({"component": "A", "name": "Documenti visti in giornata", "direction": 1 if s > 50 else 0,
                        "value": round(s, 1),
                        "explanation": f"{f.attention_docs_1d} documenti oggi (copie incluse: "
                                       "l'attenzione conta le pagine, la conferma conta le origini)"})
    value = combine(parts)
    return ComponentScore("A", value, cfg["weights"]["A"], factors)


def component_C(n: NarrativeStats) -> ComponentScore:
    """Fragilità del catalizzatore e qualità delle fonti. Più fragile = più alto."""
    cfg = scoring_config()
    factors, parts = [], []
    if n.total_documents == 0:
        return ComponentScore("C", None, cfg["weights"]["C"], [])

    # conferma del claim centrale: rumor non confermato = fragile
    if n.central_claim_status is not None:
        s = {"rumor": 90.0, "previsione": 75.0, "opinione": 70.0,
             "interpretazione": 60.0, "fatto": 25.0}.get(n.central_claim_status, 50.0)
        parts.append(s)
        factors.append({"component": "C", "name": "Stato del claim centrale",
                        "direction": 1 if s > 50 else -1, "value": s,
                        "explanation": f"Il claim centrale è «{n.central_claim_status}»"})
    # fonti primarie riducono la fragilità
    if n.primary_sources > 0:
        s = clamp(30.0 - 10.0 * n.primary_sources, 0, 30)
        parts.append(s)
        factors.append({"component": "C", "name": "Fonti primarie presenti", "direction": -1,
                        "value": s, "explanation": f"{n.primary_sources} fonte/i di livello 1-2"})
    else:
        parts.append(85.0)
        factors.append({"component": "C", "name": "Nessuna fonte primaria", "direction": 1,
                        "value": 85.0, "explanation": "Nessun filing o dichiarazione diretta a supporto"})
    # origini indipendenti: una sola origine = fragile (100 copie contano 1)
    if n.independent_origins <= 1:
        parts.append(80.0)
        factors.append({"component": "C", "name": "Origine unica", "direction": 1, "value": 80.0,
                        "explanation": f"{n.total_documents} documenti ma "
                                       f"{n.independent_origins} origine indipendente"})
    else:
        s = clamp(80.0 - 15.0 * (n.independent_origins - 1), 10, 80)
        parts.append(s)
        factors.append({"component": "C", "name": "Origini indipendenti", "direction": -1, "value": s,
                        "explanation": f"{n.independent_origins} origini indipendenti"})
    # duplicazione elevata = deterioramento informativo
    dup = n.duplicate_share
    if dup is not None and n.total_documents >= 3:
        s = scale(dup, 0.0, 1.0)
        parts.append(s)
        factors.append({"component": "C", "name": "Quota di duplicati", "direction": 1 if s > 50 else 0,
                        "value": round(s, 1),
                        "explanation": f"{dup:.0%} dei documenti sono riscritture"})
    # contraddizioni
    if n.contradictions > 0:
        s = clamp(60.0 + 25.0 * n.contradictions, 60, 100)
        parts.append(s)
        factors.append({"component": "C", "name": "Contraddizioni", "direction": 1, "value": s,
                        "explanation": f"{n.contradictions} contraddizione/i tra le fonti"})
    # contenuto promozionale
    if n.promo_documents > 0:
        parts.append(90.0)
        factors.append({"component": "C", "name": "Contenuto promozionale", "direction": 1, "value": 90.0,
                        "explanation": f"{n.promo_documents} contenuto/i promozionali rilevati"})
    value = combine(parts)
    return ComponentScore("C", value, cfg["weights"]["C"], factors)


def component_D(ctx: EventContext) -> ComponentScore:
    """Rischio di diluizione e struttura del capitale."""
    cfg = scoring_config()
    factors, parts = [], []
    if ctx.recent_dilution_filing:
        parts.append(90.0)
        factors.append({"component": "D", "name": "Filing di diluizione recente", "direction": 1,
                        "value": 90.0, "explanation": "S-1/S-3/424B o ATM recente"})
    if ctx.shelf_or_atm_open:
        parts.append(70.0)
        factors.append({"component": "D", "name": "Shelf/ATM con capacità residua", "direction": 1,
                        "value": 70.0,
                        "explanation": "Shelf o ATM aperti: capacità potenziale, non vendita già avvenuta"})
    if not parts:
        # nessuna informazione => componente non calcolabile (mai 0 implicito)
        return ComponentScore("D", None, cfg["weights"]["D"], [])
    value = combine(parts)
    return ComponentScore("D", value, cfg["weights"]["D"], factors)


def component_F(f: Features, ctx: EventContext) -> ComponentScore:
    """Mismatch fondamentale (proxy iniziale, vedi SCORING.md)."""
    cfg = scoring_config()
    factors, parts = [], []
    if f.ret_20d is not None:
        if ctx.has_fundamental_catalyst:
            s = scale(f.ret_20d, 0.5, 3.0) * 0.4  # catalizzatore fondamentale attenua
            explanation = "Rally con catalizzatore fondamentale dichiarato"
            direction = -1
        else:
            s = scale(f.ret_20d, 0.3, 2.0)
            explanation = "Rally 20g senza catalizzatore fondamentale identificato"
            direction = 1 if s > 50 else 0
        parts.append(s)
        factors.append({"component": "F", "name": "Mismatch prezzo/fondamentali", "direction": direction,
                        "value": round(s, 1), "explanation": explanation})
    value = combine(parts)
    return ComponentScore("F", value, cfg["weights"]["F"], factors)


def component_B(ctx: EventContext) -> ComponentScore:
    """Dipendenza da evento binario."""
    cfg = scoring_config()
    factors, parts = [], []
    if ctx.has_pending_binary:
        parts.append(95.0)
        types = ", ".join(ctx.pending_binary_types)
        factors.append({"component": "B", "name": "Evento binario pendente", "direction": 1,
                        "value": 95.0, "explanation": f"Esito binario pendente: {types}"})
    elif ctx.dominant_event_type is not None:
        binary_dominant = ctx.dominant_event_type in BINARY_EVENT_TYPES
        s = 60.0 if binary_dominant else 20.0
        parts.append(s)
        factors.append({"component": "B", "name": "Concentrazione su singolo evento",
                        "direction": 1 if s > 50 else 0, "value": s,
                        "explanation": f"Movimento guidato da: {ctx.dominant_event_type}"})
    value = combine(parts)
    return ComponentScore("B", value, cfg["weights"]["B"], factors)


# ----------------------------------------------------------------- hazard ---

def squeeze_hazard(f: Features) -> tuple[float | None, bool]:
    """(hazard, unknown). Sconosciuto se mancano le misure necessarie."""
    cfg = scoring_config()["squeeze"]
    inputs: dict[str, float | None] = {
        "short_interest_pct_float": None if f.short_interest_pct_float is None
            else scale(f.short_interest_pct_float, 0.0, 0.4),
        "days_to_cover": None if f.days_to_cover is None else scale(f.days_to_cover, 0.0, 10.0),
        "volume_over_float": None if f.volume_over_float is None else scale(f.volume_over_float, 0.0, 1.0),
        "premarket_gap": None if f.premarket_gap is None else scale(f.premarket_gap, 0.0, 0.6),
        "halts": None if f.halts_recent is None else scale(float(f.halts_recent), 0.0, 3.0),
    }
    if all(inputs.get(k) is None for k in cfg["required_any"]):
        return None, True
    total_w, acc = 0.0, 0.0
    for name, weight in cfg["weights"].items():
        v = inputs.get(name)
        if v is not None:
            acc += v * weight
            total_w += weight
    if total_w == 0:
        return None, True
    return round(acc / total_w, 1), False


def execution_hazard(f: Features) -> float | None:
    if f.asset_type == "crypto":
        # nessun modello di spread/liquidità per le crypto: hazard sconosciuto
        return None
    cfg = scoring_config()["execution"]
    inputs: dict[str, float | None] = {
        # proxy dello spread: prezzi bassi e ADV basso implicano spread peggiori
        "spread_proxy": None if f.price is None else clamp(100.0 - scale(f.price, 1.0, 20.0)),
        "adv_dollar": None if f.median_dollar_volume_20d is None
            else clamp(100.0 - scale(f.median_dollar_volume_20d, 1_000_000, 50_000_000)),
        "halts": None if f.halts_recent is None else scale(float(f.halts_recent), 0.0, 3.0),
        "price_level": None if f.price is None else (90.0 if f.price < 1.0 else 10.0),
    }
    total_w, acc = 0.0, 0.0
    for name, weight in cfg["weights"].items():
        v = inputs.get(name)
        if v is not None:
            acc += v * weight
            total_w += weight
    if total_w == 0:
        return None
    return round(acc / total_w, 1)


# ------------------------------------------------------------- confidence ---

def confidence_grade(f: Features, n: NarrativeStats, missing_components: list[str]) -> str:
    """E.8: A dati completi + fonte primaria; B mercato ok ma intelligence
    secondaria; C mancano float/economics/origine; D dati incoerenti o stale."""
    if f.stale_days is not None and f.stale_days > 3:
        return "D"
    if f.bars_available < 60:
        return "D"
    market_complete = all(x is not None for x in (f.price, f.ret_1d, f.ret_5d, f.rvol))
    if not market_complete:
        return "D"
    has_primary = n.primary_sources > 0 or n.independent_origins >= 2
    critical = scoring_config()["critical_components"]
    critical_missing = [c for c in missing_components if c in critical]
    if critical_missing:
        return "D" if len(critical_missing) > 1 else "C"
    # il float senza fonte commerciale non è disponibile in live: la sua
    # assenza esclude il grade A ma non degrada a C se market cap e mercato
    # sono completi (vedi DECISIONS.md D18)
    if f.market_cap is None:
        return "C"
    complete_for_a = f.float_shares is not None and not missing_components
    if market_complete and has_primary and complete_for_a:
        return "A"
    if market_complete:
        return "B"
    return "C"


# ------------------------------------------------------------------ gates ---

def apply_gates(f: Features, ctx: EventContext, components: dict[str, ComponentScore],
                sq_hazard: float | None, sq_unknown: bool,
                exec_hazard: float | None, universe_status: str) -> str | None:
    """Precedenza: binario > squeeze > non quantificabile > dati insufficienti."""
    cfg = scoring_config()["gates"]

    # 1. EVENTO BINARIO — EVITARE
    b = components.get("B")
    if ctx.has_pending_binary:
        return STATE_BINARY_EVENT
    if b is not None and b.value is not None and b.value >= cfg["binary_event"]["b_component_min"] \
            and ctx.dominant_event_type in cfg["binary_event"]["event_types"]:
        return STATE_BINARY_EVENT

    # 2. POSSIBILE SQUEEZE — NON ADATTO ALLO SHORT
    if sq_hazard is not None and sq_hazard >= cfg["squeeze"]["hazard_min"]:
        return STATE_POSSIBLE_SQUEEZE

    # 3. RISCHIO NON QUANTIFICABILE (illiquidità, prezzo sotto soglia, execution estremo)
    unq = cfg["unquantifiable"]
    if f.asset_type != "crypto" and f.price is not None and f.price < unq["min_price"]:
        return STATE_UNQUANTIFIABLE
    if universe_status in ("shadow_illiquid", "shadow_price"):
        return STATE_UNQUANTIFIABLE
    if exec_hazard is not None and exec_hazard >= unq["execution_hazard_min"]:
        return STATE_UNQUANTIFIABLE

    # 4. DATI INSUFFICIENTI
    ins = cfg["insufficient_data"]
    missing_components = [k for k, c in components.items() if c.missing]
    if f.bars_available < ins["require_bars"]:
        return STATE_INSUFFICIENT_DATA
    if f.stale_days is not None and f.stale_days > ins["max_stale_days"]:
        return STATE_INSUFFICIENT_DATA
    if len(missing_components) > scoring_config()["max_missing_components"]:
        return STATE_INSUFFICIENT_DATA

    return None


# ------------------------------------------------------------------ score ---

def compute_score(f: Features, n: NarrativeStats, ctx: EventContext,
                  universe_status: str = "in_universe") -> ScoreResult:
    cfg = scoring_config()
    components = {
        "R": component_R(f),
        "V": component_V(f),
        "A": component_A(f),
        "C": component_C(n),
        "D": component_D(ctx),
        "F": component_F(f, ctx),
        "B": component_B(ctx),
    }

    # rinormalizzazione sui componenti disponibili: il mancante NON vale zero
    available = {k: c for k, c in components.items() if c.value is not None}
    missing_components = [k for k, c in components.items() if c.value is None]
    risk_index: float | None = None
    if available and len(missing_components) <= cfg["max_missing_components"]:
        total_weight = sum(c.weight for c in available.values())
        risk_index = round(
            sum(c.value * c.weight for c in available.values()) / total_weight, 1
        )

    sq_hazard, sq_unknown = squeeze_hazard(f)
    exec_hazard = execution_hazard(f)
    grade = confidence_grade(f, n, missing_components)

    gate = apply_gates(f, ctx, components, sq_hazard, sq_unknown, exec_hazard, universe_status)

    if gate is not None:
        state = gate
        if gate in (STATE_UNQUANTIFIABLE, STATE_INSUFFICIENT_DATA):
            risk_index = None  # non pubblicare un numero non difendibile
    else:
        thr = cfg["thresholds"]
        if risk_index is None:
            state = STATE_INSUFFICIENT_DATA
            gate = STATE_INSUFFICIENT_DATA
        elif risk_index >= thr["elevated"] and grade in ("A", "B"):
            state = STATE_ELEVATED
        elif risk_index >= thr["monitor"]:
            state = STATE_MONITOR
        else:
            state = STATE_BELOW_THRESHOLD

    missing_data = list(dict.fromkeys(f.missing + [f"componente_{c}" for c in missing_components]))

    invalidation = _invalidation_conditions(f, n, ctx, state)

    return ScoreResult(
        risk_index=risk_index,
        components=components,
        squeeze_hazard=sq_hazard,
        squeeze_unknown=sq_unknown,
        execution_hazard=exec_hazard,
        dilution_risk=components["D"].value,
        confidence_grade=grade,
        state=state,
        gate_applied=gate,
        missing_data=missing_data,
        invalidation_conditions=invalidation,
        scoring_version=cfg["version"],
        config_hash=config_hash(),
        code_version=APP_VERSION,
    )


def _invalidation_conditions(f: Features, n: NarrativeStats, ctx: EventContext, state: str) -> list[str]:
    out = []
    if n.central_claim_status == "rumor":
        out.append("Conferma ufficiale del rumor da fonte di livello 1-2 (filing o comunicato)")
    if ctx.has_pending_binary:
        out.append("Risoluzione dell'evento binario pendente (esito positivo può produrre ulteriore gap)")
    if f.short_interest_pct_float is None:
        out.append("Pubblicazione di short interest/borrow: potrebbe rivelare rischio squeeze")
    if ctx.recent_dilution_filing:
        out.append("Completamento dell'offering: l'incasso può eliminare il rischio di solvibilità")
    if ctx.has_fundamental_catalyst:
        out.append("Conferma dei fondamentali nei prossimi filing (10-Q/10-K)")
    out.append("Nuova fonte primaria che modifica il claim centrale")
    return out
