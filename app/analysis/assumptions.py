"""Financial assumptions - every value carries its source, date and type.

type = "official"  -> taken from an official/legal source (still verify before a deal)
type = "assumption" -> a working estimate, editable in Settings; NOT a fact
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Assumption:
    key: str
    label_he: str
    value: float
    kind: str  # "official" | "assumption"
    source: str
    as_of: str
    note: str = ""


# Purchase tax for an additional (investment) apartment.
# 8% up to 6,055,070 ILS, 10% above. Temporary order valid for purchases
# until 10 Feb 2027 (Bizportal, Nov 2026). Re-check after that date.
PURCHASE_TAX_BRACKETS: list[tuple[float, float]] = [
    (6_055_070, 0.08),
    (float("inf"), 0.10),
]
PURCHASE_TAX_META = Assumption(
    key="purchase_tax",
    label_he="מס רכישה לדירה נוספת",
    value=0.08,
    kind="official",
    source="רשות המסים / Bizportal: 8% עד 6,055,070 ₪, 10% מעל",
    as_of="2026-11",
    note="הוראת שעה בתוקף לרכישות עד 10.2.2027 – יש לאמת לפני עסקה",
)

DEFAULTS: dict[str, Assumption] = {
    a.key: a
    for a in [
        Assumption("lawyer_pct", "שכר טרחת עו\"ד (כולל מע\"מ)", 0.0059, "assumption", "הערכת עבודה מקובלת בשוק", "2026-11"),
        Assumption("broker_pct", "דמי תיווך (כולל מע\"מ)", 0.0236, "assumption", "2% + מע\"מ, הערכה", "2026-11"),
        Assumption("appraiser_fixed", "שמאי, בדק בית ושונות (₪)", 6_000, "assumption", "הערכה", "2026-11"),
        Assumption("renovation_light_per_sqm", "שיפוץ קל (₪ למ\"ר)", 1_500, "assumption", "הערכה", "2026-11"),
        Assumption("renovation_full_per_sqm", "שיפוץ מלא (₪ למ\"ר)", 4_500, "assumption", "הערכה", "2026-11"),
        Assumption("vacancy_months", "חודשים ללא שוכר בשנה", 0.5, "assumption", "הערכה", "2026-11"),
        Assumption("maintenance_pct_rent", "תחזוקה (% משכ\"ד שנתי)", 0.05, "assumption", "הערכה", "2026-11"),
        Assumption("insurance_yearly", "ביטוח מבנה וצד ג' (₪ לשנה)", 1_200, "assumption", "הערכה", "2026-11"),
        Assumption("management_pct_rent", "ניהול נכס (% משכ\"ד)", 0.0, "assumption", "ללא ניהול חיצוני", "2026-11"),
    ]
}

# Scenario multipliers applied to estimated rent and to vacancy
SCENARIOS: dict[str, dict[str, float]] = {
    "conservative": {"rent_factor": 0.92, "vacancy_factor": 2.0, "label": "שמרני"},  # type: ignore[dict-item]
    "base": {"rent_factor": 1.00, "vacancy_factor": 1.0, "label": "בסיסי"},  # type: ignore[dict-item]
    "optimistic": {"rent_factor": 1.06, "vacancy_factor": 0.5, "label": "אופטימי"},  # type: ignore[dict-item]
}


def value(key: str, overrides: dict[str, float] | None = None) -> float:
    if overrides and key in overrides:
        return float(overrides[key])
    return DEFAULTS[key].value
