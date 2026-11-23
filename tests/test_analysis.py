from datetime import date, datetime

from app.analysis.analyzer import run_analysis
from app.analysis.comps import find_comps
from app.analysis.scoring import ScoreInput, score, tier
from app.collectors.govmap import store_deals
from app.database.models import Property, RentalComparable, Transaction
from app.database.db import source_by_code
from app.services.ingest import IngestResult, upsert_listing
from app.services.report import build_daily_report
from app.services.text_parser import ParsedListing

TODAY = date(2026, 11, 23)


def deal(i, price, sqm, rooms=3, street="אחד העם", d="2026-06-01", neigh="מרכז העיר"):
    return {"objectid": i, "dealAmount": price, "dealDate": d + "T00:00:00", "assetArea": sqm,
            "assetRoomNum": rooms, "streetName": street, "houseNumber": "10", "neighborhood": neigh,
            "settlementNameHeb": "פתח תקווה", "propertyTypeDescription": "דירה בבית קומות", "floor": "שניה"}


def test_store_deals_dedup(session):
    n = store_deals(session, [deal(1, 1_800_000, 70), deal(1, 1_800_000, 70), {"objectid": 2}])
    assert n == 1


def test_comps_street_level_and_outlier_removed(session):
    store_deals(session, [deal(i, 70 * (26_000 + i * 100), 70) for i in range(1, 9)] + [deal(99, 70 * 60_000, 70)])
    txs = session.query(Transaction).all()
    prop = Property(city="פתח תקווה", street="רחוב אחד העם", rooms=3, sqm=68, neighborhood="מרכז העיר")
    c = find_comps(prop, txs, TODAY)
    assert c.level == "street" and c.count == 8 and c.confidence == "high"
    assert 26_000 <= c.median_ppsqm <= 27_000


def test_comps_ignore_old_and_dissimilar(session):
    store_deals(session, [deal(1, 2_000_000, 70, d="2022-01-01"), deal(2, 4_000_000, 150, rooms=6)])
    prop = Property(city="פתח תקווה", street="אחד העם", rooms=3, sqm=70)
    assert find_comps(prop, session.query(Transaction).all(), TODAY).count == 0


def test_score_missing_data_cannot_be_high():
    s_full, _ = score(ScoreInput(value_gap_pct=0.15, comps_confidence="high", gross_yield=4.0,
                                 renewal_status="approved", condition="needs_renovation", sqm=90, rooms=3,
                                 neighborhood_demand=90, price_drops=2, total_drop_pct=0.08, completeness=1.0))
    s_thin, bd = score(ScoreInput(gross_yield=4.0, completeness=0.3))
    assert s_full >= 85 and tier(s_full) == "הזדמנות יוצאת דופן לבדיקה"
    assert s_thin < 55
    assert bd["components"]["price_gap"]["value"] is None


def test_end_to_end_analysis_and_report(session):
    store_deals(session, [deal(i, 70 * 27_000, 70) for i in range(1, 9)])
    src = source_by_code(session, "manual")
    for r in (4_800, 5_000, 5_200):
        session.add(RentalComparable(source_id=src.id, city="פתח תקווה", neighborhood="מרכז העיר", rooms=3,
                                     monthly_rent=r, observed_at=TODAY, origin="user"))
    r = IngestResult()
    upsert_listing(session, ParsedListing(
        source_code="manual", external_id="x1", city="פתח תקווה", street="אחד העם", house_number="61",
        neighborhood="מרכז העיר", asking_price=1_690_000, rooms=3, sqm=70, floor=3, elevator=True, parking=False,
        condition="good", url="https://example.com/1",
        found_fields=["asking_price", "rooms", "sqm", "floor", "street", "neighborhood", "elevator", "parking", "condition"],
    ), r, now=datetime(2026, 11, 23, 6))
    res = run_analysis(session, (1_000_000, 1_800_000), today=TODAY)
    assert len(res) == 1
    a = res[0]
    assert a.est_value == 1_890_000 and a.value_gap_pct > 0.1
    assert a.est_rent == 5_000 and a.gross_yield == round(5_000 * 12 / 1_690_000 * 100, 2)
    assert set(a.scenarios) == {"conservative", "base", "optimistic"}
    assert a.score > 0 and "components" in a.score_breakdown
    text = build_daily_report(session, datetime(2026, 11, 23, 8), 5)
    assert "אחד העם 61" in text and "חדש" in text and "1,690,000" in text


def test_out_of_budget_skipped(session):
    upsert_listing(session, ParsedListing(source_code="manual", external_id="big", city="פתח תקווה",
                                          asking_price=2_500_000, rooms=4, sqm=100), IngestResult())
    assert run_analysis(session, (1_000_000, 1_800_000), today=TODAY) == []
