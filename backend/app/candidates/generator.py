"""Candidate generator deterministico.

Un titolo entra tra i candidati con ALMENO UNA condizione di accelerazione
E ALMENO UNA condizione di conferma (soglie in config/candidates.yaml).
Ogni candidato registra regole attivate, valori osservati e dati mancanti.
Il filtro riduce l'universo: non attribuisce da solo rischio elevato.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.candidates.features import Features
from app.config import candidates_config


@dataclass
class RuleHit:
    rule: str
    kind: str          # acceleration | confirmation
    observed: float | bool | None
    threshold: float | bool | None
    description: str

    def to_dict(self) -> dict:
        return {
            "rule": self.rule, "kind": self.kind,
            "observed": self.observed, "threshold": self.threshold,
            "description": self.description,
        }


@dataclass
class CandidateDecision:
    is_candidate: bool
    hits: list[RuleHit]
    universe_status: str  # in_universe | shadow_illiquid | shadow_price | shadow_cap | no_data
    missing: list[str]

    def reasons(self) -> list[dict]:
        return [h.to_dict() for h in self.hits]


def evaluate(features: Features, asof: date) -> CandidateDecision:
    cfg = candidates_config()
    acc_cfg, conf_cfg, uni = cfg["acceleration"], cfg["confirmation"], cfg["universe"]
    hits: list[RuleHit] = []
    f = features

    if f.blocked_unreconciled_action:
        return CandidateDecision(False, [], "no_data", f.missing)
    if f.bars_available == 0:
        return CandidateDecision(False, [], "no_data", f.missing)

    # --- universo / universo ombra (mai scambiare non-modellabilità per assenza di rischio)
    universe_status = "in_universe"
    is_crypto = f.asset_type == "crypto"
    if not is_crypto and f.price is not None and f.price < uni["min_price"]:
        universe_status = "shadow_price"
    elif not is_crypto and f.market_cap is not None \
            and not (uni["min_market_cap"] <= f.market_cap <= uni["max_market_cap"]):
        universe_status = "shadow_cap"
    elif (f.median_dollar_volume_20d is not None
          and f.median_dollar_volume_20d < uni["min_median_dollar_volume_20d"]):
        universe_status = "shadow_illiquid"

    # --- condizioni di accelerazione
    if f.ret_1d is not None and f.ret_1d >= acc_cfg["ret_1d_min"]:
        hits.append(RuleHit("ret_1d", "acceleration", round(f.ret_1d, 4), acc_cfg["ret_1d_min"],
                            f"Rendimento 1g {f.ret_1d:+.1%} ≥ {acc_cfg['ret_1d_min']:.0%}"))
    if f.gap is not None and f.gap >= acc_cfg["gap_min"]:
        hits.append(RuleHit("gap", "acceleration", round(f.gap, 4), acc_cfg["gap_min"],
                            f"Gap {f.gap:+.1%} ≥ {acc_cfg['gap_min']:.0%}"))
    if f.premarket_gap is not None and f.premarket_gap >= acc_cfg["gap_min"]:
        hits.append(RuleHit("premarket_gap", "acceleration", round(f.premarket_gap, 4), acc_cfg["gap_min"],
                            f"Gap pre-market {f.premarket_gap:+.1%} ≥ {acc_cfg['gap_min']:.0%}"))
    if f.ret_5d is not None and f.ret_5d >= acc_cfg["ret_5d_min"]:
        hits.append(RuleHit("ret_5d", "acceleration", round(f.ret_5d, 4), acc_cfg["ret_5d_min"],
                            f"Rendimento 5g {f.ret_5d:+.1%} ≥ {acc_cfg['ret_5d_min']:.0%}"))
    if f.ret_20d is not None and f.ret_20d >= acc_cfg["ret_20d_min"]:
        hits.append(RuleHit("ret_20d", "acceleration", round(f.ret_20d, 4), acc_cfg["ret_20d_min"],
                            f"Rendimento 20g {f.ret_20d:+.1%} ≥ {acc_cfg['ret_20d_min']:.0%}"))
    if f.robust_z_ret is not None and f.robust_z_ret >= acc_cfg["robust_z_min"]:
        hits.append(RuleHit("robust_z_ret", "acceleration", round(f.robust_z_ret, 2), acc_cfg["robust_z_min"],
                            f"Robust-z rendimento {f.robust_z_ret:.1f} ≥ {acc_cfg['robust_z_min']}"))

    has_acceleration = any(h.kind == "acceleration" for h in hits)

    # --- condizioni di conferma
    if f.rvol is not None and f.rvol >= conf_cfg["rvol_min"]:
        hits.append(RuleHit("rvol", "confirmation", round(f.rvol, 2), conf_cfg["rvol_min"],
                            f"Volume relativo {f.rvol:.1f}× ≥ {conf_cfg['rvol_min']}×"))
    if f.turnover_float is not None and f.turnover_float >= 0.5:
        # proxy semplice del percentile 95 di turnover; il percentile
        # sull'universo completo richiede il cross-section (modalità live)
        hits.append(RuleHit("turnover", "confirmation", round(f.turnover_float, 3), 0.5,
                            f"Turnover sul flottante {f.turnover_float:.0%} anomalo"))
    if f.attention_z is not None and f.attention_z >= conf_cfg["attention_z_min"]:
        hits.append(RuleHit("attention_z", "confirmation", round(f.attention_z, 2), conf_cfg["attention_z_min"],
                            f"Attenzione robust-z {f.attention_z:.1f} ≥ {conf_cfg['attention_z_min']}"))
    if conf_cfg.get("material_event") and f.new_material_event:
        hits.append(RuleHit("material_event", "confirmation", True, True,
                            "Nuovo evento materiale classificato"))

    has_confirmation = any(h.kind == "confirmation" for h in hits)

    is_candidate = has_acceleration and has_confirmation
    return CandidateDecision(is_candidate, hits, universe_status, f.missing)
