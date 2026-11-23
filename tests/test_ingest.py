from datetime import datetime

from sqlalchemy import select

from app.database.models import Listing, PriceHistory, Property
from app.services.ingest import IngestResult, mark_missing_as_removed, representative_listings, upsert_listing
from app.services.text_parser import ParsedListing


def P(**kw):
    base = dict(source_code="yad2", external_id="a1", city="פתח תקווה", street="אחד העם", house_number="61",
                asking_price=1_700_000, rooms=3, sqm=66, floor=3, found_fields=["asking_price", "rooms", "sqm"])
    base.update(kw)
    return ParsedListing(**base)


def test_new_then_price_drop_keeps_history(session):
    r = IngestResult()
    l = upsert_listing(session, P(), r, now=datetime(2026, 11, 1))
    assert r.new_listings == [l.id]
    upsert_listing(session, P(asking_price=1_650_000), r, now=datetime(2026, 11, 5))
    assert r.price_drops == [(l.id, 1_700_000, 1_650_000)]
    hist = session.execute(select(PriceHistory).where(PriceHistory.listing_id == l.id)).scalars().all()
    assert [h.change for h in hist] == ["initial", "drop"]
    assert [h.price for h in hist] == [1_700_000, 1_650_000]


def test_cross_source_duplicate_same_property(session):
    r = IngestResult()
    a = upsert_listing(session, P(), r)
    b = upsert_listing(session, P(source_code="madlan", external_id="m9", street="רח' אחד-העם", sqm=67), r)
    assert a.property_id == b.property_id
    assert r.cross_source_dups == [b.id]
    assert len(session.execute(select(Property)).scalars().all()) == 1
    reps = representative_listings(session)
    assert len(reps) == 1


def test_different_floor_is_different_property(session):
    r = IngestResult()
    a = upsert_listing(session, P(), r)
    b = upsert_listing(session, P(source_code="madlan", external_id="m2", floor=1), r)
    assert a.property_id != b.property_id


def test_removed_and_relisted(session):
    r = IngestResult()
    l = upsert_listing(session, P(), r)
    removed = mark_missing_as_removed(session, "yad2", set())
    assert removed == [l.id] and l.status == "removed"
    upsert_listing(session, P(), r)
    assert l.status == "active" and l.relisted_count == 1 and r.relisted == [l.id]
    assert session.execute(select(Listing)).scalars().all() == [l]  # history kept, no duplicate row
