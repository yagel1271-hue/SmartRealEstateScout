"""Upsert listings: dedup, cross-source matching, price history, relists.

History is never deleted. Each call returns events used by alerts/report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.db import source_by_code
from app.database.models import Listing, PriceHistory, Property, utcnow
from app.services.normalize import norm_address, norm_city
from app.services.text_parser import ParsedListing

PROPERTY_FIELDS = [
    "neighborhood", "street", "house_number", "rooms", "sqm", "floor", "building_floors",
    "year_built", "elevator", "parking", "balcony", "mamad", "condition",
]


@dataclass
class IngestResult:
    new_listings: list[int] = field(default_factory=list)
    price_drops: list[tuple[int, int, int]] = field(default_factory=list)  # (listing_id, old, new)
    price_rises: list[tuple[int, int, int]] = field(default_factory=list)
    relisted: list[int] = field(default_factory=list)
    cross_source_dups: list[int] = field(default_factory=list)
    updated: int = 0


def _close(a: float | None, b: float | None, tol: float) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def find_matching_property(s: Session, p: ParsedListing) -> Property | None:
    city = norm_city(p.city)
    addr = norm_address(city, p.street, p.house_number)
    q = select(Property).where(Property.city == city)
    candidates = list(s.execute(q).scalars())
    for prop in candidates:
        if addr and prop.norm_address == addr:
            if (p.rooms is None or prop.rooms is None or _close(p.rooms, prop.rooms, 0.5)) and (
                p.sqm is None or prop.sqm is None or _close(p.sqm, prop.sqm, 5)
            ) and (p.floor is None or prop.floor is None or p.floor == prop.floor):
                return prop
    # No address: strict match on neighborhood + rooms + sqm + floor
    if not addr and p.neighborhood and p.rooms and p.sqm and p.floor is not None:
        for prop in candidates:
            if (
                prop.neighborhood == p.neighborhood
                and _close(p.rooms, prop.rooms, 0)
                and _close(p.sqm, prop.sqm, 3)
                and prop.floor == p.floor
            ):
                return prop
    return None


def _apply_property_fields(prop: Property, p: ParsedListing) -> None:
    for f in PROPERTY_FIELDS:
        v = getattr(p, f)
        if v is not None and getattr(prop, f) is None:
            setattr(prop, f, v)
    if prop.norm_address is None:
        prop.norm_address = norm_address(prop.city, prop.street, prop.house_number)


def upsert_listing(s: Session, p: ParsedListing, result: IngestResult, now: datetime | None = None) -> Listing:
    now = now or utcnow()
    src = source_by_code(s, p.source_code)
    origin = {f: "listing" for f in p.found_fields}
    listing = s.execute(
        select(Listing).where(Listing.source_id == src.id, Listing.external_id == p.external_id)
    ).scalar_one_or_none()

    if listing:
        listing.last_seen = now
        if listing.status == "removed":
            listing.status = "active"
            listing.relisted_count += 1
            result.relisted.append(listing.id)
            if p.asking_price:
                s.add(PriceHistory(listing=listing, price=p.asking_price, observed_at=now, change="relist"))
        if p.asking_price and listing.asking_price and p.asking_price != listing.asking_price:
            old = listing.asking_price
            change = "drop" if p.asking_price < old else "rise"
            s.add(PriceHistory(listing=listing, price=p.asking_price, observed_at=now, change=change))
            (result.price_drops if change == "drop" else result.price_rises).append((listing.id, old, p.asking_price))
            listing.asking_price = p.asking_price
            listing.last_updated = now
        elif p.asking_price and not listing.asking_price:
            listing.asking_price = p.asking_price
            s.add(PriceHistory(listing=listing, price=p.asking_price, observed_at=now, change="initial"))
        if p.known_rent:
            listing.known_rent = p.known_rent
        listing.field_origin = {**(listing.field_origin or {}), **origin}
        _apply_property_fields(listing.property, p)
        result.updated += 1
        return listing

    prop = find_matching_property(s, p)
    is_dup = prop is not None
    if prop is None:
        prop = Property(city=norm_city(p.city) or "")
        s.add(prop)
    _apply_property_fields(prop, p)

    listing = Listing(
        property=prop,
        source_id=src.id,
        external_id=p.external_id,
        url=p.url,
        asking_price=p.asking_price,
        known_rent=p.known_rent,
        description=p.description,
        first_seen=now,
        last_seen=now,
        last_updated=now,
        status="active",
        field_origin=origin,
    )
    s.add(listing)
    s.flush()
    if p.asking_price:
        s.add(PriceHistory(listing=listing, price=p.asking_price, observed_at=now, change="initial"))
    if is_dup:
        result.cross_source_dups.append(listing.id)
        older_removed = [l for l in prop.listings if l.id != listing.id and l.status == "removed"]
        if older_removed:
            listing.relisted_count = 1
            result.relisted.append(listing.id)
    else:
        result.new_listings.append(listing.id)
    return listing


def mark_missing_as_removed(s: Session, source_code: str, seen_external_ids: set[str], now: datetime | None = None) -> list[int]:
    """For AUTOMATED listing sources only: listings not seen in a full scan become 'removed'."""
    now = now or utcnow()
    src = source_by_code(s, source_code)
    removed = []
    for l in s.execute(select(Listing).where(Listing.source_id == src.id, Listing.status == "active")).scalars():
        if l.external_id not in seen_external_ids:
            l.status = "removed"
            l.last_updated = now
            removed.append(l.id)
    return removed


def representative_listings(s: Session) -> list[Listing]:
    """One active listing per property (lowest price) - avoids duplicates in analysis/reports."""
    best: dict[int, Listing] = {}
    for l in s.execute(select(Listing).where(Listing.status == "active")).scalars():
        cur = best.get(l.property_id)
        if cur is None or (l.asking_price or 10**12) < (cur.asking_price or 10**12):
            best[l.property_id] = l
    return list(best.values())
