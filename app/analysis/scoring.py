"""Opportunity score 0-100 with a transparent breakdown.

Each component returns 0..1 or None (= not assessable, data missing).
Weights of assessable components are re-normalised, then the total is
multiplied by a data-completeness factor so that a listing with missing
data can never score high. The score is a screening tool, not advice.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_WEIGHTS = {
    "price_gap": 0.25,
    "rental_yield": 0.25,
    "urban_renewal": 0.20,
    "value_add": 0.15,
    "location": 0.10,
    "negotiation": 0.05,
}

LABELS_HE = {
    "price_gap": "פער ממחיר עסקאות השוואה",
    "rental_yield": "תשואה משכירות",
    "urban_renewal": "פוטנציאל התחדשות עירונית",
    "value_add": "פוטנציאל השבחה ושיפוץ",
    "location": "מיקום וביקוש לשכירות",
    "negotiation": "גמישות מחיר ומשא ומתן",
}

TIERS = [(85, "הזדמנות יוצאת דופן לבדיקה"), (70, "הזדמנות מעניינת"), (55, "דורשת בדיקה נוספת"), (0, "עדיפות נמוכה")]


def tier(score: float | None) -> str:
    if score is None:
        return "לא דורג"
    for th, label in TIERS:
        if score >= th:
            return label
    return TIERS[-1][1]


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class ScoreInput:
    value_gap_pct: float | None = None       # +0.10 = asking 10% below estimate
    comps_confidence: str = "none"
    gross_yield: float | None = None          # % on price
    renewal_status: str | None = None         # approved | deposited | planning | declared | none | None
    condition: str | None = None
    sqm: float | None = None
    rooms: float | None = None
    neighborhood_demand: float | None = None  # 0..100 when data exists
    price_drops: int = 0
    total_drop_pct: float = 0.0
    days_on_market: int | None = None
    completeness: float = 0.0                 # 0..1 share of key fields known


CONF_FACTOR = {"high": 1.0, "medium": 0.85, "low": 0.6, "none": 0.0}
RENEWAL_SCORE = {"approved": 1.0, "deposited": 0.8, "planning": 0.5, "declared": 0.6, "none": 0.0}


def components(x: ScoreInput) -> dict[str, float | None]:
    c: dict[str, float | None] = {}
    if x.value_gap_pct is not None and x.comps_confidence != "none":
        # -10% (overpriced) -> 0, +15% below estimate -> 1
        c["price_gap"] = _clamp((x.value_gap_pct + 0.10) / 0.25) * CONF_FACTOR[x.comps_confidence]
    else:
        c["price_gap"] = None
    # 2.0% -> 0, 4.0% -> 1 (gross, on price)
    c["rental_yield"] = None if x.gross_yield is None else _clamp((x.gross_yield - 2.0) / 2.0)
    c["urban_renewal"] = None if x.renewal_status is None else RENEWAL_SCORE.get(x.renewal_status, 0.0)
    layout_known = bool(x.sqm and x.rooms)
    if x.condition is None and not layout_known:
        c["value_add"] = None
    else:
        v = 0.0
        if x.condition == "needs_renovation":
            v += 0.6
        elif x.condition == "good":
            v += 0.3
        if layout_known and x.sqm / x.rooms >= 28:
            v += 0.3  # generous layout - possible extra room/re-plan
        c["value_add"] = _clamp(v)
    c["location"] = None if x.neighborhood_demand is None else _clamp(x.neighborhood_demand / 100)
    neg = 0.0
    if x.price_drops:
        neg += min(0.6, 0.3 * x.price_drops) + _clamp(x.total_drop_pct / 0.10) * 0.2
    if x.days_on_market is not None and x.days_on_market > 60:
        neg += 0.2
    c["negotiation"] = _clamp(neg)
    return c


def score(x: ScoreInput, weights: dict[str, float] | None = None) -> tuple[float, dict]:
    w = weights or DEFAULT_WEIGHTS
    comps = components(x)
    assessed = {k: v for k, v in comps.items() if v is not None}
    wsum = sum(w[k] for k in assessed)
    raw = sum(w[k] * v for k, v in assessed.items()) / wsum if wsum else 0.0
    coverage = wsum / sum(w.values())
    # Missing data penalty: completeness of listing fields and of assessable weight
    data_factor = 0.5 + 0.5 * min(x.completeness, coverage)
    total = round(100 * raw * data_factor, 1)
    breakdown = {
        "components": {
            k: {"label": LABELS_HE[k], "weight": w[k], "value": None if v is None else round(v, 3),
                "points": None if v is None else round(100 * w[k] * v / wsum * data_factor, 1) if wsum else 0}
            for k, v in comps.items()
        },
        "weight_coverage": round(coverage, 2),
        "completeness": round(x.completeness, 2),
        "data_factor": round(data_factor, 2),
        "tier": tier(total),
    }
    return total, breakdown
