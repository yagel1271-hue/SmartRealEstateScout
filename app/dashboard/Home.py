"""Smart Real Estate Scout - Streamlit dashboard (Hebrew, RTL, read-only)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.analysis import assumptions as A  # noqa: E402
from app.analysis.scoring import DEFAULT_WEIGHTS, LABELS_HE, tier  # noqa: E402
from app.config import get_settings, score_weights  # noqa: E402
from app.database.db import init_db, session_scope  # noqa: E402
from app.database.models import (  # noqa: E402
    Analysis,
    Favorite,
    Listing,
    PriceHistory,
    ScanHistory,
    Source,
    Transaction,
)

st.set_page_config(page_title="Smart Real Estate Scout", page_icon="🏠", layout="wide")
st.markdown(
    """
    <style>
      .stApp, .block-container, [data-testid="stSidebar"] { direction: rtl; text-align: right; }
      [data-testid="stMetricValue"], [data-testid="stMetricLabel"] { direction: rtl; }
      .stDataFrame, .js-plotly-plot { direction: ltr; }
      .small { font-size: 0.85rem; color: #666; }
      .tag { display:inline-block; padding:2px 8px; border-radius:10px; background:#eef3ff; margin-left:4px; font-size:0.8rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

CONF_HE = {"high": "גבוהה", "medium": "בינונית", "low": "נמוכה", "none": "אין", None: "אין"}
ORIGIN_HE = {"listing": "מהמודעה", "official": "רשמי", "computed": "חושב", "ai": "הערכת AI", "user": "הוזן ע\"י המשתמש"}
RENT_ORIGIN_HE = {"listing": "מהמודעה", "rent_comps_neighborhood": "הערכה – שכונה", "rent_comps_city": "הערכה – עיר", None: "—"}


@st.cache_data(ttl=300)
def load() -> dict:
    init_db()
    with session_scope() as s:
        sources = {x.id: x for x in s.execute(select(Source)).scalars()}
        analyses = {a.listing_id: a for a in s.execute(select(Analysis).where(Analysis.is_latest.is_(True))).scalars()}
        listings = list(s.execute(select(Listing)).scalars())
        rows = []
        for l in listings:
            p = l.property
            a = analyses.get(l.id)
            rows.append({
                "id": l.id, "status": l.status, "source": sources[l.source_id].name, "source_code": sources[l.source_id].code,
                "url": l.url, "street": p.street, "house": p.house_number, "neighborhood": p.neighborhood, "city": p.city,
                "price": l.asking_price, "rooms": p.rooms, "sqm": p.sqm, "floor": p.floor,
                "building_floors": p.building_floors, "year_built": p.year_built, "elevator": p.elevator,
                "parking": p.parking, "balcony": p.balcony, "mamad": p.mamad, "condition": p.condition,
                "first_seen": l.first_seen, "last_seen": l.last_seen, "description": l.description,
                "field_origin": l.field_origin or {}, "property_id": l.property_id,
                "ppsqm": a.price_per_sqm if a else None,
                "comps_median": a.comps_median_ppsqm if a else None,
                "comps_count": a.comps_count if a else 0,
                "comps_conf": a.comps_confidence if a else None,
                "est_value": a.est_value if a else None,
                "gap": a.value_gap_pct if a else None,
                "rent": a.est_rent if a else None, "rent_origin": a.rent_origin if a else None,
                "gross_yield": a.gross_yield if a else None, "net_yield": a.net_yield_base if a else None,
                "score": a.score if a else None, "analysis": a,
            })
        df = pd.DataFrame(rows)
        for col in ("price", "rooms", "sqm", "floor", "ppsqm", "comps_median", "est_value", "gap", "rent",
                    "gross_yield", "net_yield", "score"):
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        prices = pd.DataFrame([{"listing_id": h.listing_id, "price": h.price, "date": h.observed_at, "change": h.change}
                               for h in s.execute(select(PriceHistory)).scalars()])
        tx = pd.DataFrame([{"date": t.deal_date, "price": t.price, "sqm": t.sqm, "rooms": t.rooms, "floor": t.floor,
                            "street": t.street, "house": t.house_number, "neighborhood": t.neighborhood,
                            "type": t.property_type}
                           for t in s.execute(select(Transaction)).scalars()])
        scans = pd.DataFrame([{"kind": x.kind, "start": x.started_at, "status": x.status, "stats": x.stats, "error": x.error}
                              for x in s.execute(select(ScanHistory).order_by(ScanHistory.id.desc()).limit(30)).scalars()])
        favs = {f.listing_id for f in s.execute(select(Favorite)).scalars()}
    return {"df": df, "prices": prices, "tx": tx, "scans": scans, "favs": favs}


def money(v) -> str:  # noqa: ANN001
    return "—" if v is None or pd.isna(v) else f"{int(v):,} ₪"


def address(r) -> str:  # noqa: ANN001
    a = " ".join(str(x) for x in [r["street"], r["house"]] if x and not pd.isna(x))
    return a or "כתובת לא ידועה"


data = load()
cfg = get_settings()
df = data["df"]

st.title("🏠 Smart Real Estate Scout")
st.caption(f"{', '.join(cfg.cities)} · תקציב {cfg.budget_min:,}–{cfg.budget_max:,} ₪ · "
           "הציון והערכת השווי הם כלי סינון בלבד ואינם שומה או המלצת השקעה")

tabs = st.tabs(["סקירה", "נכסים", "כרטיס נכס", "עסקאות רשמיות", "מועדפים", "סריקות", "הגדרות"])

active = df[df["status"] == "active"] if not df.empty else df
in_budget = active[(active["price"] >= cfg.budget_min) & (active["price"] <= cfg.budget_max)] if not active.empty else active

with tabs[0]:
    if df.empty:
        st.info("אין עדיין מודעות. שלח קישור/טקסט של מודעה לבוט ב-Telegram, או הוסף שורה לקובץ inbox/listings.csv ב-GitHub.")
    else:
        week_ago = pd.Timestamp.now() - pd.Timedelta(days=7)
        c = st.columns(6)
        c[0].metric("מודעות פעילות", len(active))
        c[1].metric("בתקציב", len(in_budget))
        c[2].metric("חדשות (7 ימים)", int((active["first_seen"] >= week_ago).sum()))
        drops = data["prices"]
        c[3].metric("ירידות מחיר", 0 if drops.empty else int((drops["change"] == "drop").sum()))
        c[4].metric("הזדמנויות (ציון ≥70)", int((in_budget["score"].fillna(0) >= 70).sum()))
        c[5].metric("תשואה ברוטו ממוצעת", "—" if in_budget["gross_yield"].dropna().empty else f"{in_budget['gross_yield'].mean():.2f}%")
        c2 = st.columns(2)
        c2[0].metric("מחיר ממוצע למ\"ר (בתקציב)", "—" if in_budget["ppsqm"].dropna().empty else f"{in_budget['ppsqm'].mean():,.0f} ₪")
        c2[1].metric("עסקאות רשמיות במערכת", len(data["tx"]))
        if not in_budget.empty:
            by_n = in_budget.assign(neighborhood=in_budget["neighborhood"].fillna("לא ידוע")).groupby("neighborhood").agg(
                count=("id", "count"), avg_score=("score", "mean")).reset_index()
            st.plotly_chart(px.bar(by_n, x="neighborhood", y="count", color="avg_score",
                                   labels={"neighborhood": "שכונה", "count": "מודעות", "avg_score": "ציון ממוצע"},
                                   title="הזדמנויות לפי שכונה"), use_container_width=True)
            st.subheader("מובילות")
            for _, r in in_budget.sort_values("score", ascending=False).head(5).iterrows():
                st.markdown(f"**{address(r)}** · {r['neighborhood'] or ''} · {money(r['price'])} · "
                            f"ציון **{(r['score'] or 0):.0f}** – {tier(r['score'])}"
                            + (f" · [למודעה]({r['url']})" if r["url"] else ""))

with tabs[1]:
    if active.empty:
        st.info("אין מודעות פעילות.")
    else:
        f = st.columns(5)
        neighs = sorted(x for x in active["neighborhood"].dropna().unique())
        sel_n = f[0].multiselect("שכונה", neighs)
        pmin, pmax = f[1].slider("מחיר (אלפי ₪)", 500, 4000, (cfg.budget_min // 1000, cfg.budget_max // 1000), step=50)
        rooms = f[2].slider("חדרים", 1.0, 7.0, (1.0, 7.0), step=0.5)
        min_y = f[3].number_input("תשואה ברוטו מינ' %", 0.0, 10.0, 0.0, step=0.1)
        min_s = f[4].number_input("ציון מינ'", 0, 100, 0)
        q = st.text_input("חיפוש חופשי (רחוב, תיאור)")
        v = active.copy()
        if sel_n:
            v = v[v["neighborhood"].isin(sel_n)]
        v = v[(v["price"].fillna(0) >= pmin * 1000) & (v["price"].fillna(0) <= pmax * 1000)]
        v = v[(v["rooms"].isna()) | ((v["rooms"] >= rooms[0]) & (v["rooms"] <= rooms[1]))]
        if min_y:
            v = v[v["gross_yield"].fillna(0) >= min_y]
        if min_s:
            v = v[v["score"].fillna(0) >= min_s]
        if q:
            v = v[v.apply(lambda r: q in f"{r['street']} {r['neighborhood']} {r['description']}", axis=1)]
        table = pd.DataFrame({
            "#": v["id"], "כתובת": v.apply(address, axis=1), "שכונה": v["neighborhood"], "מחיר": v["price"],
            "חדרים": v["rooms"], "מ\"ר": v["sqm"], "קומה": v["floor"], "למ\"ר": v["ppsqm"],
            "חציון עסקאות למ\"ר": v["comps_median"], "פער %": (v["gap"] * 100).round(1),
            "שכ\"ד משוער": v["rent"], "תשואה ברוטו %": v["gross_yield"], "ציון": v["score"], "מודעה": v["url"],
        }).sort_values("ציון", ascending=False)
        st.dataframe(table, hide_index=True, use_container_width=True,
                     column_config={"מודעה": st.column_config.LinkColumn("מודעה", display_text="פתח"),
                                    "מחיר": st.column_config.NumberColumn(format="%d"),
                                    "ציון": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f")})

with tabs[2]:
    if df.empty:
        st.info("אין נכסים.")
    else:
        opts = {f"#{r['id']} · {address(r)} · {money(r['price'])}": r["id"] for _, r in df.sort_values("score", ascending=False).iterrows()}
        pick = st.selectbox("בחר נכס", list(opts))
        r = df[df["id"] == opts[pick]].iloc[0]
        a = r["analysis"]
        st.subheader(f"{address(r)} – {r['neighborhood'] or ''}")
        st.markdown(f"מקור: **{r['source']}** · נקלט לראשונה: {r['first_seen']:%d/%m/%Y} · סטטוס: {r['status']}"
                    + (f" · [פתח מודעה]({r['url']})" if r["url"] else "")
                    + (" · ⭐ במועדפים" if r["id"] in data["favs"] else ""))
        c = st.columns(4)
        c[0].metric("מחיר מבוקש", money(r["price"]))
        c[1].metric("ציון", "—" if r["score"] is None or pd.isna(r["score"]) else f"{r['score']:.0f}", tier(r["score"]))
        c[2].metric("הערכת שווי (סינון)", money(r["est_value"]),
                    None if r["gap"] is None or pd.isna(r["gap"]) else f"{r['gap']*100:+.1f}% מול המחיר")
        c[3].metric("תשואה ברוטו", "—" if r["gross_yield"] is None or pd.isna(r["gross_yield"]) else f"{r['gross_yield']:.2f}%")

        st.markdown("#### פרטי הנכס ומקור כל נתון")
        fo = r["field_origin"]
        fields = [("rooms", "חדרים"), ("sqm", "מ\"ר"), ("floor", "קומה"), ("building_floors", "קומות בבניין"),
                  ("year_built", "שנת בנייה"), ("elevator", "מעלית"), ("parking", "חניה"), ("balcony", "מרפסת"),
                  ("mamad", "ממ\"ד"), ("condition", "מצב")]
        st.dataframe(pd.DataFrame([{"שדה": he, "ערך": "לא ידוע" if r[k] is None or (not isinstance(r[k], str) and pd.isna(r[k])) else r[k],
                                    "מקור": ORIGIN_HE.get(fo.get(k), "—")} for k, he in fields]),
                     hide_index=True, use_container_width=True)

        if a is not None:
            st.markdown("#### השוואה לעסקאות רשמיות (רשות המסים / GovMap)")
            st.markdown(f"עסקאות דומות: **{a.comps_count}** · אמינות: **{CONF_HE.get(a.comps_confidence)}** · "
                        f"חציון למ\"ר: {money(a.comps_median_ppsqm)} · ממוצע: {money(a.comps_mean_ppsqm)} · "
                        f"טווח: {money(a.comps_min_ppsqm)}–{money(a.comps_max_ppsqm)} · למ\"ר בנכס: {money(a.price_per_sqm)}")
            if a.comps_sample:
                st.dataframe(pd.DataFrame(a.comps_sample).rename(columns={
                    "date": "תאריך", "price": "מחיר", "sqm": "מ\"ר", "rooms": "חדרים", "floor": "קומה",
                    "street": "רחוב", "house": "מס'", "ppsqm": "למ\"ר"}), hide_index=True, use_container_width=True)
            st.caption("הערכת השווי = חציון מחיר למ\"ר של עסקאות דומות × שטח הנכס. זו אינה שומה מקצועית.")

            st.markdown("#### עלויות ותשואה")
            if a.costs:
                cost_he = {"price": "מחיר", "purchase_tax": "מס רכישה (דירה נוספת)", "lawyer": "עו\"ד", "broker": "תיווך",
                           "other": "שמאי/בדק בית/שונות", "renovation": "שיפוץ (הערכה)", "total_investment": "סה\"כ השקעה"}
                st.dataframe(pd.DataFrame([{"סעיף": cost_he.get(k, k), "₪": v} for k, v in a.costs.items()]),
                             hide_index=True, use_container_width=True)
            st.markdown(f"שכ\"ד חודשי: **{money(a.est_rent)}** ({RENT_ORIGIN_HE.get(a.rent_origin, 'הערכה')})")
            if a.scenarios:
                st.dataframe(pd.DataFrame(a.scenarios).T.rename(columns={
                    "label": "תרחיש", "monthly_rent": "שכ\"ד", "vacancy_months": "חודשים ריקים", "annual_income": "הכנסה שנתית",
                    "annual_expenses": "הוצאות", "noi": "הכנסה נטו", "gross_yield_on_price": "ברוטו על המחיר %",
                    "gross_yield_on_total": "ברוטו על סה\"כ %", "net_yield_on_total": "נטו על סה\"כ %"}).drop(columns=["scenario"]),
                    use_container_width=True)

            st.markdown("#### התחדשות עירונית")
            ren = a.renewal or {}
            if ren.get("status") == "match":
                st.markdown(f"מתחם: **{ren.get('name')}** · סטטוס רשמי: **{ren.get('official_status')}** · תוכנית: {ren.get('plan') or '—'}"
                            + (f" · [מקור]({ren['url']})" if ren.get("url") else ""))
            else:
                st.markdown(ren.get("note") or "לא נבדק")

            st.markdown("#### פירוט הציון")
            bd = a.score_breakdown or {}
            comp = bd.get("components", {})
            st.dataframe(pd.DataFrame([{"רכיב": v["label"], "משקל": f"{v['weight']*100:.0f}%",
                                        "ערך (0–1)": "לא נבדק – חסר מידע" if v["value"] is None else v["value"],
                                        "נקודות": v["points"]} for v in comp.values()]),
                         hide_index=True, use_container_width=True)
            st.caption(f"כיסוי נתונים: {bd.get('weight_coverage', 0)*100:.0f}% מהמשקל · שלמות פרטי מודעה: "
                       f"{bd.get('completeness', 0)*100:.0f}% · מקדם קנס על חוסר נתונים: ×{bd.get('data_factor', 0)}")
            if a.flags:
                st.warning(" · ".join(a.flags))

        ph = data["prices"]
        ph = ph[ph["listing_id"] == r["id"]] if not ph.empty else ph
        if not ph.empty:
            st.markdown("#### היסטוריית מחיר")
            st.plotly_chart(px.line(ph, x="date", y="price", markers=True, labels={"date": "תאריך", "price": "מחיר"}),
                            use_container_width=True)
        if r["description"]:
            with st.expander("תיאור המודעה"):
                st.write(r["description"])

with tabs[3]:
    tx = data["tx"]
    if tx.empty:
        st.info("עדיין לא נמשכו עסקאות. הן נמשכות אוטומטית סביב כל נכס שנקלט.")
    else:
        tx = tx.assign(ppsqm=(tx["price"] / tx["sqm"]).round())
        st.markdown(f"{len(tx)} עסקאות רשמיות · מקור: GovMap / רשות המסים")
        st.plotly_chart(px.scatter(tx.dropna(subset=["ppsqm"]), x="date", y="ppsqm", color="neighborhood",
                                   hover_data=["street", "house", "rooms", "sqm", "price"],
                                   labels={"date": "תאריך", "ppsqm": "₪ למ\"ר", "neighborhood": "שכונה"}),
                        use_container_width=True)
        st.dataframe(tx.sort_values("date", ascending=False), hide_index=True, use_container_width=True)

with tabs[4]:
    favs = df[df["id"].isin(data["favs"])] if not df.empty else df
    if favs.empty:
        st.info("אין מועדפים. שלח לבוט: /fav מספר-מודעה")
    else:
        for _, r in favs.iterrows():
            st.markdown(f"#{r['id']} **{address(r)}** · {money(r['price'])} · ציון {(r['score'] or 0):.0f}")

with tabs[5]:
    if data["scans"].empty:
        st.info("עדיין לא היו סריקות.")
    else:
        st.dataframe(data["scans"], hide_index=True, use_container_width=True)

with tabs[6]:
    st.markdown("ההגדרות נשמרות בקובץ `config/settings.json` ב-GitHub – לחיצה על העיפרון בקובץ, עריכה ו-Commit. "
                "השינוי ייכנס לתוקף בהרצה הבאה.")
    st.json({"ערים": list(cfg.cities), "תקציב": [cfg.budget_min, cfg.budget_max], "שעת דוח": cfg.daily_report_time,
             "סף התראה מיידית": cfg.instant_alert_score})
    w = {**DEFAULT_WEIGHTS, **(score_weights() or {})}
    st.markdown("**משקולות הדירוג**")
    st.dataframe(pd.DataFrame([{"רכיב": LABELS_HE[k], "משקל": f"{v*100:.0f}%"} for k, v in w.items()]), hide_index=True)
    st.markdown("**הנחות פיננסיות** (official = ממקור רשמי, assumption = הערכת עבודה)")
    rows = [{"פרמטר": A.PURCHASE_TAX_META.label_he, "ערך": "8% עד 6,055,070 ₪, 10% מעל", "סוג": "official",
             "מקור": A.PURCHASE_TAX_META.source, "נכון ל": A.PURCHASE_TAX_META.as_of, "הערה": A.PURCHASE_TAX_META.note}]
    rows += [{"פרמטר": x.label_he, "ערך": x.value, "סוג": x.kind, "מקור": x.source, "נכון ל": x.as_of, "הערה": x.note}
             for x in A.DEFAULTS.values()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
