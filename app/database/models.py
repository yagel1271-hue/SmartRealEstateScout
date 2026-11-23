"""Database schema (SQLAlchemy 2.0). SQLite now, PostgreSQL-ready.

Provenance rule: every listing/transaction row keeps its source and fetch
time; listings also keep `field_origin` = {field: "listing"|"official"|
"computed"|"ai"|"user"} so verified data and estimates are never mixed.
History is never deleted: price changes go to price_history, disappeared
listings get status="removed".
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))  # listing | transactions | index | renewal | manual
    url: Mapped[str | None] = mapped_column(String(300))
    automated: Mapped[bool] = mapped_column(Boolean, default=False)
    terms_note: Mapped[str | None] = mapped_column(Text)
    reliability: Mapped[str] = mapped_column(String(20), default="reported")  # official | reported | estimated


class Neighborhood(Base):
    __tablename__ = "neighborhoods"
    __table_args__ = (UniqueConstraint("city", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    city: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    rent_demand: Mapped[int | None] = mapped_column(Integer)  # 0-100, filled when data exists
    notes: Mapped[str | None] = mapped_column(Text)


class Property(Base):
    """A physical apartment. Several listings (sources/re-posts) can point to it."""
    __tablename__ = "properties"
    id: Mapped[int] = mapped_column(primary_key=True)
    city: Mapped[str] = mapped_column(String(60), index=True)
    neighborhood: Mapped[str | None] = mapped_column(String(120), index=True)
    street: Mapped[str | None] = mapped_column(String(120))
    house_number: Mapped[str | None] = mapped_column(String(20))
    norm_address: Mapped[str | None] = mapped_column(String(200), index=True)
    rooms: Mapped[float | None] = mapped_column(Float)
    sqm: Mapped[float | None] = mapped_column(Float)
    floor: Mapped[int | None] = mapped_column(Integer)
    building_floors: Mapped[int | None] = mapped_column(Integer)
    year_built: Mapped[int | None] = mapped_column(Integer)
    property_type: Mapped[str | None] = mapped_column(String(40))
    elevator: Mapped[bool | None] = mapped_column(Boolean)
    parking: Mapped[bool | None] = mapped_column(Boolean)
    balcony: Mapped[bool | None] = mapped_column(Boolean)
    mamad: Mapped[bool | None] = mapped_column(Boolean)
    condition: Mapped[str | None] = mapped_column(String(40))  # new | renovated | good | needs_renovation
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    listings: Mapped[list["Listing"]] = relationship(back_populates="property")


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        Index("ix_listings_status_price", "status", "asking_price"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String(80))
    url: Mapped[str | None] = mapped_column(String(500))
    asking_price: Mapped[int | None] = mapped_column(Integer)
    known_rent: Mapped[int | None] = mapped_column(Integer)  # rent stated in listing/by user
    description: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[date | None] = mapped_column(Date)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | removed | sold
    relisted_count: Mapped[int] = mapped_column(Integer, default=0)
    field_origin: Mapped[dict] = mapped_column(JSON, default=dict)
    images: Mapped[list] = mapped_column(JSON, default=list)

    property: Mapped[Property] = relationship(back_populates="listings")
    source: Mapped[Source] = relationship()
    prices: Mapped[list["PriceHistory"]] = relationship(back_populates="listing", order_by="PriceHistory.observed_at")


class PriceHistory(Base):
    __tablename__ = "price_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    price: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    change: Mapped[str] = mapped_column(String(20))  # initial | drop | rise | relist
    listing: Mapped[Listing] = relationship(back_populates="prices")


class Transaction(Base):
    """Recorded sale from the official registry (GovMap / Tax Authority)."""
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_tx_city_neigh_date", "city", "neighborhood", "deal_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String(80), unique=True)
    deal_date: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[int] = mapped_column(Integer)
    sqm: Mapped[float | None] = mapped_column(Float)
    rooms: Mapped[float | None] = mapped_column(Float)
    floor: Mapped[int | None] = mapped_column(Integer)
    city: Mapped[str | None] = mapped_column(String(60))
    neighborhood: Mapped[str | None] = mapped_column(String(120))
    street: Mapped[str | None] = mapped_column(String(120))
    house_number: Mapped[str | None] = mapped_column(String(20))
    property_type: Mapped[str | None] = mapped_column(String(60))
    year_built: Mapped[int | None] = mapped_column(Integer)
    deal_type: Mapped[str | None] = mapped_column(String(20))  # new | second_hand
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class RentalComparable(Base):
    __tablename__ = "rental_comparables"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    city: Mapped[str] = mapped_column(String(60))
    neighborhood: Mapped[str | None] = mapped_column(String(120))
    rooms: Mapped[float | None] = mapped_column(Float)
    sqm: Mapped[float | None] = mapped_column(Float)
    monthly_rent: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[date] = mapped_column(Date)
    origin: Mapped[str] = mapped_column(String(20))  # official_index | listing | user
    url: Mapped[str | None] = mapped_column(String(500))


class UrbanRenewal(Base):
    __tablename__ = "urban_renewal"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    city: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(200))
    track: Mapped[str | None] = mapped_column(String(60))  # pinui-binui | tama38 | ...
    status: Mapped[str] = mapped_column(String(80))  # exactly as the official source states
    plan_number: Mapped[str | None] = mapped_column(String(60))
    streets: Mapped[list] = mapped_column(JSON, default=list)
    units_existing: Mapped[int | None] = mapped_column(Integer)
    units_planned: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(String(500))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Analysis(Base):
    __tablename__ = "analysis"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    price_per_sqm: Mapped[float | None] = mapped_column(Float)
    comps_count: Mapped[int] = mapped_column(Integer, default=0)
    comps_median_ppsqm: Mapped[float | None] = mapped_column(Float)
    comps_mean_ppsqm: Mapped[float | None] = mapped_column(Float)
    comps_min_ppsqm: Mapped[float | None] = mapped_column(Float)
    comps_max_ppsqm: Mapped[float | None] = mapped_column(Float)
    comps_confidence: Mapped[str | None] = mapped_column(String(20))  # high | medium | low | none
    est_value: Mapped[int | None] = mapped_column(Integer)
    value_gap_pct: Mapped[float | None] = mapped_column(Float)  # (est_value - price)/price
    est_rent: Mapped[int | None] = mapped_column(Integer)
    rent_origin: Mapped[str | None] = mapped_column(String(40))
    gross_yield: Mapped[float | None] = mapped_column(Float)
    net_yield_base: Mapped[float | None] = mapped_column(Float)
    scenarios: Mapped[dict] = mapped_column(JSON, default=dict)
    costs: Mapped[dict] = mapped_column(JSON, default=dict)
    renewal: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float | None] = mapped_column(Float, index=True)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    comps_sample: Mapped[list] = mapped_column(JSON, default=list)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"))
    kind: Mapped[str] = mapped_column(String(30))  # daily_report | instant | price_drop
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    message: Mapped[str | None] = mapped_column(Text)


class Favorite(Base):
    __tablename__ = "favorites"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), unique=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ScanHistory(Base):
    __tablename__ = "scan_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | ok | partial | failed
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
