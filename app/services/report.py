"""Build the daily Telegram report (Hebrew, HTML parse mode)."""
from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scoring import tier
from app.database.models import Analysis, Listing, PriceHistory, utcnow

CONF_HE = {"high": "גבוהה", "medium": "בינונית", "low": "נמוכה", "none": "אין"}
RENT_ORIGIN_HE = {"listing": "מהמודעה", "rent_comps_neighborhood": "הערכה – שכונה", "rent_comps_city": "הערכה – עיר"}


def fmt_money(v: float | int | None) -> str:
    return "—" if v is None else f"{int(round(v)):,} ₪"


def listing_title(l: Listing) -> str:
    p = l.property
    addr = " ".join(x for x in [p.street, p.house_number] if x) or "כתובת לא ידועה"
    parts = [addr]
    if p.neighborhood:
        parts.append(p.neighborhood)
    return escape(", ".join(parts))


def listing_block(l: Listing, a: Analysis | None, tags: list[str] | None = None) -> str:
    p = l.property
    lines = [f"<b>{listing_title(l)}</b>" + (f"  [{' · '.join(tags)}]" if tags else "")]
    spec = []
    if p.rooms:
        spec.append(f"{p.rooms:g} חד'")
    if p.sqm:
        spec.append(f"{p.sqm:g} מ\"ר")
    if p.floor is not None:
        spec.append(f"קומה {p.floor}")
    lines.append(f"{fmt_money(l.asking_price)} | " + " | ".join(spec))
    if a:
        if a.price_per_sqm and a.comps_median_ppsqm:
            gap = f"{a.value_gap_pct*100:+.0f}%" if a.value_gap_pct is not None else ""
            lines.append(
                f"למ\"ר: {a.price_per_sqm:,.0f} מול חציון עסקאות {a.comps_median_ppsqm:,.0f} "
                f"({a.comps_count} עסקאות, אמינות {CONF_HE.get(a.comps_confidence or 'none')}) {gap}"
            )
        if a.est_rent and a.gross_yield is not None:
            lines.append(f"שכ\"ד {fmt_money(a.est_rent)} ({RENT_ORIGIN_HE.get(a.rent_origin or '', 'הערכה')}) · "
                         f"תשואה ברוטו {a.gross_yield:.2f}% · נטו (בסיסי) {a.net_yield_base:.2f}%")
        lines.append(f"ציון: <b>{a.score:.0f}</b> – {tier(a.score)}")
    if l.url:
        lines.append(f"<a href=\"{escape(l.url)}\">למודעה</a>")
    return "\n".join(lines)


def build_daily_report(s: Session, now: datetime, max_items: int = 5, tz_label: str = "") -> str:
    since = utcnow() - timedelta(days=1)  # DB times are UTC; `now` is local, display only
    latest = {a.listing_id: a for a in s.execute(select(Analysis).where(Analysis.is_latest.is_(True))).scalars()}
    listings = {l.id: l for l in s.execute(select(Listing).where(Listing.id.in_(latest.keys()))).scalars()} if latest else {}
    new_ids = [lid for lid, l in listings.items() if l.first_seen >= since]
    drops = {
        h.listing_id for h in s.execute(
            select(PriceHistory).where(PriceHistory.change == "drop", PriceHistory.observed_at >= since)
        ).scalars()
    }
    ranked = sorted(latest.values(), key=lambda a: a.score or 0, reverse=True)

    out = [f"🏠 <b>Smart Real Estate Scout – דוח יומי</b>\n{now:%d/%m/%Y %H:%M} {tz_label}".strip()]
    out.append(f"נכסים פעילים בתקציב: {len(latest)} · חדשים: {len(new_ids)} · ירידות מחיר: {len(drops & set(listings))}")

    if not latest:
        out.append("אין עדיין מודעות במערכת.\nשלח לבוט קישור או טקסט של מודעה (יד2/מדלן/תיווך) והמערכת תנתח אותה מול עסקאות רשמיות.")
        return "\n\n".join(out)

    shown = 0
    blocks = []
    for a in ranked:
        if shown >= max_items:
            break
        if (a.score or 0) < 40 and a.listing_id not in drops and a.listing_id not in new_ids:
            continue
        l = listings[a.listing_id]
        tags = []
        if a.listing_id in new_ids:
            tags.append("חדש")
        if a.listing_id in drops:
            tags.append("ירידת מחיר")
        if a.value_gap_pct is not None and a.value_gap_pct >= 0.05 and a.comps_confidence in ("medium", "high"):
            tags.append("מתחת לעסקאות")
        if a.gross_yield and a.gross_yield >= 3.2:
            tags.append("תשואה")
        blocks.append(listing_block(l, a, tags))
        shown += 1
    if blocks:
        out.append("<b>הזדמנויות מובילות</b>")
        out.extend(blocks)
    else:
        out.append("אין היום הזדמנויות שעוברות את סף האיכות.")
    out.append("<i>הציון והערכת השווי הם כלי סינון בלבד ואינם שומה או המלצת השקעה.</i>")
    return "\n\n".join(out)
