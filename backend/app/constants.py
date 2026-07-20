"""Costanti condivise: stati, tassonomie, livelli fonte."""
from __future__ import annotations

# --- Stati finali (ordine = precedenza dei gate; il gate prevale sullo score) ---
STATE_BINARY_EVENT = "EVENTO BINARIO — EVITARE"
STATE_POSSIBLE_SQUEEZE = "POSSIBILE SQUEEZE — NON ADATTO ALLO SHORT"
STATE_UNQUANTIFIABLE = "RISCHIO NON QUANTIFICABILE"
STATE_INSUFFICIENT_DATA = "DATI INSUFFICIENTI"
STATE_ELEVATED = "RISCHIO DI CORREZIONE ELEVATO"
STATE_MONITOR = "MONITORARE"
STATE_BELOW_THRESHOLD = "SOTTO SOGLIA"  # non mostrato nella lista primaria

GATE_PRECEDENCE = [
    STATE_BINARY_EVENT,
    STATE_POSSIBLE_SQUEEZE,
    STATE_UNQUANTIFIABLE,
    STATE_INSUFFICIENT_DATA,
]

ALL_STATES = GATE_PRECEDENCE + [STATE_ELEVATED, STATE_MONITOR, STATE_BELOW_THRESHOLD]

# --- Confidence ---
CONFIDENCE_GRADES = ["A", "B", "C", "D"]

# --- Tassonomia eventi (chiusa; l'event classifier non può inventarne altri) ---
EVENT_TYPES = [
    "clinical_readout_positive",
    "clinical_readout_negative",
    "clinical_readout_pending",
    "clinical_milestone",          # es. "ultimo paziente dosato": NON è un risultato
    "fda_decision_pending",
    "fda_approval",
    "fda_crl",
    "ma_confirmed",
    "ma_rumor",
    "ma_rumor_denied",
    "partnership",
    "offering_or_dilution",        # shelf, ATM, 424B, warrant, convertibili
    "insider_activity",            # Form 4 / 144 (contesto, non segnale bearish automatico)
    "earnings_surprise",
    "guidance_change",
    "index_inclusion",
    "reverse_split",
    "delisting_notice",
    "going_concern",
    "court_ruling_pending",
    "court_ruling",
    "promotion_suspected",
    "meme_attention",
    "sector_pivot",                # pivot AI/crypto/quantum
    "halt",
    "other_material",
]

BINARY_EVENT_TYPES = {
    "clinical_readout_pending",
    "fda_decision_pending",
    "ma_rumor",
    "ma_confirmed",
    "court_ruling_pending",
}

# --- Stato dei claim ---
CLAIM_STATUSES = ["fatto", "rumor", "opinione", "interpretazione", "previsione"]

# --- Relazioni tra claim ---
CLAIM_RELATIONS = ["conferma", "contraddice", "cita", "riscrive", "deriva_da"]

# --- Gerarchia delle fonti (D.1 della ricerca) ---
SOURCE_LEVELS = {
    1: "Filing, autorità, documento giudiziario o regolatorio",
    2: "Dichiarazione diretta di società o autorità",
    3: "Agenzia con reporting e fonti proprie",
    4: "Articolo che cita e collega una fonte primaria",
    5: "Analisi finanziaria o scientifica",
    6: "Rumor attribuito a fonti anonime",
    7: "Post di un utente identificabile",
    8: "Opinione non verificata",
    9: "Contenuto promozionale o sponsorizzato",
    10: "Riscrittura automatica o duplicato",
}
PRIMARY_SOURCE_LEVELS = {1, 2}

# --- Stato licenza / conservazione dei documenti ---
LICENSE_STATES = ["metadata_only", "excerpt_allowed", "full_allowed", "unknown"]

# --- Data quality ---
ISSUE_TYPES = [
    "missing_bar",
    "stale_source",
    "provider_not_configured",
    "unreconciled_corporate_action",
    "missing_timestamp",
    "impossible_ohlc",
    "ai_output_rejected",
    "ingestion_error",
    "signal_suppressed",
]

# --- Orizzonti retrospettivi (sedute) ---
RETRO_HORIZONS = [1, 3, 5, 10, 20]
RETRO_THRESHOLDS = [-0.10, -0.20, -0.30, -0.40]
PRIMARY_LABEL = {"threshold": -0.20, "horizon": 10}  # DD_10 <= -20%

DISCLAIMER = (
    "Strumento personale di ricerca. Non è consulenza finanziaria, non promette "
    "rendimenti e non prevede crolli con certezza. Il Risk Index è un indice "
    "ordinale, non una probabilità. Un rischio elevato di drawdown NON implica "
    "che il titolo sia shortabile: eventi binari e squeeze possono rendere "
    "estremamente pericolosa qualsiasi operazione."
)
