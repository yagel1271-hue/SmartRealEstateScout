"""Run the full analysis for active listings and store results in `analysis`."""
from __future__ import annotations

import logging
import statistics
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.analysis import finance
from app.analysis.comps import find_comps
from app.analysis.scoring import DEFAULT_WEIGHTS, ScoreInput, score
from app.config import score_weights
from app.database.models import (
    Analysis,
    Listing,
    Neighborhood,
    PriceHistory,
    RentalComparable,
    Transaction,
    UrbanRenewal,
)
from app.services.ingest import representative_listings
from app.services.normalize import norm_street

log = logging.getLogger("scout.analyzer")
KEY_FIELDS = ["asking_price", "rooms", "sqm", "floor", "street", "neighborhood", "condition", "elevator", "parking"]


def completeness(l: Listing) -> float:
    p = l.property
    have = sum(
        1 for f in KEY_FIELDS
        if (getattr(l, f, None) if f == "asking_price" else getattr(p, f, None)) is not None
    )
    return have / len(KEY_FIELDS)


def estimate_rent(s: Session, l: Listing) -> tuple[int | None, str | None]:
    if l.known_rent:
        return l.known_rent, "listing"
    p = l.property
    if not p.rooms:
        return None, None
    q = select(RentalComparable).where(RentalComparable.city == p.city)
    rows = [r for r in s.execute(q).scalars() if r.rooms is None or abs(r.rooms - p.rooms) <= 0.5]
    near = [r for r in rows if p.neighborhood and r.neighborhood and (r.neighborhood in p.neighborhood or p.neighborhood in r.neighborhood)]
    use = near if len(near) >= 3 else rows
    if len(use) < 3:
        return None, None
    origin = "rent_comps_neighborhood" if use is near else "rent_comps_city"
    return int(statistics.median(r.monthly_rent for r in use)), origin


def renewal_for(s: Session, l: Listing) -> dict:
    p = l.property
    rows = list(s.execute(select(UrbanRenewal).where(UrbanRenewal.city == p.city)).scalars())
    if not rows:
        return {"status": None, "note": "אין עדיין נתוני התחדשות עירונית רשמיים במערכת"}
    st = norm_street(p.street)
    for r in rows:
        tokens = [norm_street(x) for x in (r.streets or [])] + [norm_street(r.name)]
        if st and any(tk and (st in tk or tk in st) for tk in tokens if tk and len(tk) >= 3):
            return {"status": "match", "match": "street", "name": r.name, "track": r.track, "plan": r.plan_number,
                    "official_status": r.status, "url": r.source_url,
                    "note": "התאמה לפי שם רחוב בשם המתחם – יש לאמת בתוכנית (מבא\"ת) שהבניין כלול בה"}
    if p.neighborhood:
        for r in rows:
            if p.neighborhood in r.name:
                return {"status": "match", "match": "neighborhood", "name": r.name, "track": r.track,
                        "plan": r.plan_number, "official_status": r.status, "url": r.source_url,
                        "note": "מתחם באותה שכונה – לא בהכרח כולל את הבניין"}
    if not st:
        return {"status": None, "note": "חסרה כתובת – לא ניתן לבדוק התאמה למתחם"}
    return {"status": "none", "note": "הרחוב לא מופיע בשמות המתחמים הרשמיים"}


def _renewal_bucket(ren: dict) -> str | None:
    status = ren.get("status")
    if status is None:
        return None
    if status == "none":
        return "none"
    t = ren.get("official_status") or ""
    if "מאושרת" in t or "אושר" in t:
        b = "approved"
    elif "הופקד" in t or "הפקדה" in t:
        b = "deposited"
    elif "סטטוטורי" in t:
        b = "planning"
    else:
        b = "initial"
    return b if ren.get("match") == "street" else f"{b}_area"


def analyze_listing(s: Session, l: Listing, transactions: list[Transaction], today: date | None = None) -> Analysis:
    today = today or date.today()
    p = l.property
    a = Analysis(listing_id=l.id, flags=[])
    price = l.asking_price
    if price and p.sqm:
        a.price_per_sqm = round(price / p.sqm)

    comps = find_comps(p, transactions, today)
    a.comps_count = comps.count
    a.comps_median_ppsqm = comps.median_ppsqm
    a.comps_mean_ppsqm = comps.mean_ppsqm
    a.comps_min_ppsqm = comps.min_ppsqm
    a.comps_max_ppsqm = comps.max_ppsqm
    a.comps_confidence = comps.confidence
    a.comps_sample = comps.sample
    if comps.median_ppsqm and p.sqm and price:
        a.est_value = int(round(comps.median_ppsqm * p.sqm, -3))
        a.value_gap_pct = round((a.est_value - price) / price, 4)
    else:
        a.flags.append("אין מספיק עסקאות השוואה דומות")

    rent, origin = estimate_rent(s, l)
    a.est_rent, a.rent_origin = rent, origin
    if price:
        costs = finance.purchase_costs(price, p.sqm, p.condition)
        a.costs = costs.as_dict()
        if rent:
            a.gross_yield = round(finance.gross_yield(rent, price), 2)
            a.scenarios = finance.all_scenarios(rent, costs)
            a.net_yield_base = a.scenarios["base"]["net_yield_on_total"]
        else:
            a.flags.append("אין נתון שכירות – התשואה לא חושבה")

    ren = renewal_for(s, l)
    a.renewal = ren
    neigh = None
    if p.neighborhood:
        neigh = s.execute(select(Neighborhood).where(Neighborhood.city == p.city, Neighborhood.name == p.neighborhood)).scalar_one_or_none()

    prices = s.execute(select(PriceHistory).where(PriceHistory.listing_id == l.id).order_by(PriceHistory.observed_at)).scalars().all()
    drops = [h for h in prices if h.change == "drop"]
    first_price = prices[0].price if prices else price
    total_drop = (first_price - price) / first_price if first_price and price and first_price > price else 0.0
    days = (today - (l.published_at or l.first_seen.date())).days

    x = ScoreInput(
        value_gap_pct=a.value_gap_pct,
        comps_confidence=comps.confidence,
        gross_yield=a.gross_yield,
        renewal_status=_renewal_bucket(ren),
        condition=p.condition,
        sqm=p.sqm,
        rooms=p.rooms,
        neighborhood_demand=neigh.rent_demand if neigh and neigh.rent_demand is not None else None,
        price_drops=len(drops),
        total_drop_pct=total_drop,
        days_on_market=days,
        completeness=completeness(l),
    )
    weights = {**DEFAULT_WEIGHTS, **(score_weights() or {})}
    a.score, a.score_breakdown = score(x, weights)
    return a


def run_analysis(s: Session, budget: tuple[int, int] | None = None, today: date | None = None) -> list[Analysis]:
    transactions = list(s.execute(select(Transaction)).scalars())
    results = []
    s.execute(update(Analysis).values(is_latest=False))
    for l in representative_listings(s):
        if budget and l.asking_price and not (budget[0] <= l.asking_price <= budget[1]):
            continue
        a = analyze_listing(s, l, transactions, today)
        a.is_latest = True
        s.add(a)
        results.append(a)
    s.flush()
    log.info("Analyzed %d listings", len(results))
    return results
