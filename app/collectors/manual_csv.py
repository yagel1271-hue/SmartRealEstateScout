"""Manual listings from inbox/listings.csv (editable directly on github.com).

Columns (header row required, any order, empty = unknown):
url, city, neighborhood, street, house_number, price, rooms, sqm, floor,
building_floors, year_built, elevator, parking, balcony, mamad, condition,
rent, description
Booleans: כן/לא or yes/no or 1/0.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from app.services.normalize import parse_floor, parse_int
from app.services.text_parser import MADLAN_RE, YAD2_RE, ParsedListing

BOOL_TRUE = {"כן", "yes", "y", "1", "true", "יש"}
BOOL_FALSE = {"לא", "no", "n", "0", "false", "אין"}


def _bool(v: str | None) -> bool | None:
    if v is None:
        return None
    t = v.strip().lower()
    if t in BOOL_TRUE:
        return True
    if t in BOOL_FALSE:
        return False
    return None


def _float(v: str | None) -> float | None:
    try:
        return float(v.replace(",", "")) if v and v.strip() else None
    except ValueError:
        return None


def read_inbox_csv(path: Path, default_city: str) -> list[ParsedListing]:
    if not path.exists():
        return []
    out: list[ParsedListing] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if not any(row.values()):
                continue
            url = row.get("url") or None
            source, ext = "manual", None
            if url and (m := YAD2_RE.search(url)):
                source, ext = "yad2", m.group(1)
            elif url and (m := MADLAN_RE.search(url)):
                source, ext = "madlan", m.group(1)
            if not ext:
                key = "|".join(row.get(k, "") for k in ("url", "street", "house_number", "rooms", "sqm", "floor"))
                ext = "csv-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
            p = ParsedListing(
                source_code=source,
                external_id=ext,
                url=url,
                city=row.get("city") or default_city,
                neighborhood=row.get("neighborhood") or None,
                street=row.get("street") or None,
                house_number=row.get("house_number") or None,
                asking_price=parse_int(row.get("price")),
                rooms=_float(row.get("rooms")),
                sqm=_float(row.get("sqm")),
                floor=parse_floor(row.get("floor")) if row.get("floor") else None,
                building_floors=parse_int(row.get("building_floors")),
                year_built=parse_int(row.get("year_built")),
                elevator=_bool(row.get("elevator")),
                parking=_bool(row.get("parking")),
                balcony=_bool(row.get("balcony")),
                mamad=_bool(row.get("mamad")),
                condition=row.get("condition") or None,
                known_rent=parse_int(row.get("rent")),
                description=row.get("description") or None,
            )
            p.found_fields = [
                f for f in ("asking_price", "rooms", "sqm", "floor", "street", "neighborhood", "year_built",
                            "elevator", "parking", "balcony", "mamad", "condition", "known_rent")
                if getattr(p, f) is not None
            ]
            out.append(p)
    return out
