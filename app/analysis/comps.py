"""Comparable-sales selection and statistics (official transactions only).

Only genuinely similar deals are used: same city, same street or
neighborhood, rooms within +-1, area within +-25%, last 24 months,
residential types. Outliers removed by IQR. Confidence depends on count
and closeness. The estimate is a screening figure, NOT an appraisal.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.database.models import Property, Transaction
from app.services.normalize import norm_street

RESIDENTIAL_HINTS = ("דירה", "דירת", "דופלקס", "פנטהאוז", "גג", "קוטג", "מגורים")


@dataclass
class CompsResult:
    count: int = 0
    median_ppsqm: float | None = None
    mean_ppsqm: float | None = None
    min_ppsqm: float | None = None
    max_ppsqm: float | None = None
    median_price: float | None = None
    date_from: date | None = None
    date_to: date | None = None
    level: str = "none"  # street | neighborhood | none
    confidence: str = "none"  # high | medium | low | none
    sample: list[dict] = field(default_factory=list)


def _is_residential(t: Transaction) -> bool:
    return not t.property_type or any(h in t.property_type for h in RESIDENTIAL_HINTS)


def _similar(t: Transaction, prop: Property) -> bool:
    if not t.sqm or t.sqm < 20 or not t.price:
        return False
    if prop.rooms and t.rooms and abs(t.rooms - prop.rooms) > 1:
        return False
    if prop.sqm and abs(t.sqm - prop.sqm) / prop.sqm > 0.25:
        return False
    return _is_residential(t)


def _iqr_filter(values: list[float]) -> list[float]:
    if len(values) < 5:
        return values
    q = statistics.quantiles(values, n=4)
    lo, hi = q[0] - 1.5 * (q[2] - q[0]), q[2] + 1.5 * (q[2] - q[0])
    return [v for v in values if lo <= v <= hi]


def find_comps(prop: Property, transactions: list[Transaction], today: date | None = None,
               months: int = 24) -> CompsResult:
    today = today or date.today()
    since = today - timedelta(days=months * 31)
    pool = [t for t in transactions if t.deal_date >= since and _similar(t, prop)]
    street = norm_street(prop.street)
    level = "none"
    chosen: list[Transaction] = []
    if street:
        chosen = [t for t in pool if norm_street(t.street) == street]
        level = "street" if chosen else level
    if len(chosen) < 3 and prop.neighborhood:
        neigh = [t for t in pool if t.neighborhood and (t.neighborhood in prop.neighborhood or prop.neighborhood in t.neighborhood)]
        if len(neigh) > len(chosen):
            chosen, level = neigh, "neighborhood"
    if not chosen:
        return CompsResult()

    pairs = [(t.price / t.sqm, t) for t in chosen]
    kept_vals = set(_iqr_filter([v for v, _ in pairs]))
    pairs = [(v, t) for v, t in pairs if v in kept_vals]
    vals = [v for v, _ in pairs]
    n = len(vals)
    if n >= 8 and level == "street":
        conf = "high"
    elif n >= 5:
        conf = "medium" if level == "street" or n >= 10 else "low"
    elif n >= 3:
        conf = "low"
    else:
        conf = "low" if n else "none"
    pairs.sort(key=lambda x: x[1].deal_date, reverse=True)
    return CompsResult(
        count=n,
        median_ppsqm=round(statistics.median(vals)),
        mean_ppsqm=round(statistics.fmean(vals)),
        min_ppsqm=round(min(vals)),
        max_ppsqm=round(max(vals)),
        median_price=statistics.median([t.price for _, t in pairs]),
        date_from=min(t.deal_date for _, t in pairs),
        date_to=max(t.deal_date for _, t in pairs),
        level=level,
        confidence=conf,
        sample=[
            {"date": t.deal_date.isoformat(), "price": t.price, "sqm": t.sqm, "rooms": t.rooms, "floor": t.floor,
             "street": t.street, "house": t.house_number, "ppsqm": round(v)}
            for v, t in pairs[:15]
        ],
    )
