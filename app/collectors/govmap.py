"""Official recorded sale transactions via GovMap's public real-estate API.

Public, free, no key. Data originates in the Israel Tax Authority deals
registry. We send few, polite, rate-limited requests and cache results in
the `transactions` table (each deal stored once, keyed by objectid).
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.db import source_by_code
from app.database.models import Transaction, utcnow
from app.services.normalize import parse_floor

log = logging.getLogger("scout.govmap")
BASE = "https://www.govmap.gov.il/api"
UA = "SmartRealEstateScout/1.0 (personal investment research; low volume)"


class GovmapClient:
    def __init__(self, min_interval: float = 1.0, timeout: float = 30.0):
        self.s = requests.Session()
        self.s.headers.update({"Content-Type": "application/json", "User-Agent": UA, "Accept": "application/json"})
        self.min_interval = min_interval
        self.timeout = timeout
        self._last = 0.0

    def _wait(self) -> None:
        dt = time.monotonic() - self._last
        if dt < self.min_interval:
            time.sleep(self.min_interval - dt)
        self._last = time.monotonic()

    def _get(self, url: str, params: dict | None = None):
        for attempt in range(3):
            self._wait()
            try:
                r = self.s.get(url, params=params, timeout=self.timeout)
                if r.status_code in (429, 502, 503, 504):
                    time.sleep(2 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException as exc:
                if attempt == 2:
                    raise
                log.warning("GET %s failed (%s), retrying", url, exc)
                time.sleep(2 * (attempt + 1))
        return None

    def _post(self, url: str, payload: dict):
        for attempt in range(3):
            self._wait()
            try:
                r = self.s.post(url, json=payload, timeout=self.timeout)
                r.raise_for_status()
                return r.json()
            except requests.RequestException as exc:
                if attempt == 2:
                    raise
                log.warning("POST %s failed (%s), retrying", url, exc)
                time.sleep(2 * (attempt + 1))
        return None

    def autocomplete(self, text: str) -> list[dict]:
        data = self._post(f"{BASE}/search-service/autocomplete",
                          {"searchText": text, "language": "he", "isAccurate": False, "maxResults": 5})
        return (data or {}).get("results", [])

    @staticmethod
    def point_of(result: dict) -> tuple[float, float] | None:
        shape = result.get("shape") or ""
        if shape.startswith("POINT("):
            try:
                x, y = shape[6:-1].split()
                return float(x), float(y)
            except ValueError:
                return None
        return None

    def polygons_near(self, point: tuple[float, float], radius: int = 150) -> list[dict]:
        data = self._get(f"{BASE}/real-estate/deals/{point[0]},{point[1]}/{radius}")
        return data if isinstance(data, list) else []

    def _deals(self, kind: str, polygon_id: str, months_back: int, limit: int, deal_type: int) -> list[dict]:
        end = date.today()
        start = end - timedelta(days=months_back * 31)
        params = {"limit": limit, "dealType": deal_type, "startDate": start.strftime("%Y-%m"), "endDate": end.strftime("%Y-%m")}
        data = self._get(f"{BASE}/real-estate/{kind}/{polygon_id}", params)
        if isinstance(data, dict):
            return data.get("data") or []
        return data if isinstance(data, list) else []

    def street_deals(self, polygon_id: str, months_back: int = 24, limit: int = 100, deal_type: int = 2) -> list[dict]:
        return self._deals("street-deals", polygon_id, months_back, limit, deal_type)

    def neighborhood_deals(self, polygon_id: str, months_back: int = 24, limit: int = 200, deal_type: int = 2) -> list[dict]:
        return self._deals("neighborhood-deals", polygon_id, months_back, limit, deal_type)


def _parse_date(v) -> date | None:  # noqa: ANN001
    if not v:
        return None
    try:
        return date.fromisoformat(str(v).split("T")[0])
    except ValueError:
        try:
            return datetime.strptime(str(v)[:10], "%d/%m/%Y").date()
        except ValueError:
            return None


def store_deals(s: Session, deals: list[dict], deal_type: int = 2) -> int:
    src = source_by_code(s, "govmap_deals")
    added = 0
    seen: set[str] = set()
    for d in deals:
        oid = d.get("objectid") or d.get("objectId") or d.get("id")
        amount = d.get("dealAmount")
        ddate = _parse_date(d.get("dealDate"))
        if oid is None or not amount or ddate is None:
            continue
        ext = str(oid)
        if ext in seen or s.execute(select(Transaction.id).where(Transaction.external_id == ext)).first():
            continue
        seen.add(ext)
        rooms = d.get("assetRoomNum")
        s.add(Transaction(
            source_id=src.id,
            external_id=ext,
            deal_date=ddate,
            price=int(float(amount)),
            sqm=float(d["assetArea"]) if d.get("assetArea") else None,
            rooms=float(rooms) if rooms not in (None, "") else None,
            floor=d.get("floorNumber") if isinstance(d.get("floorNumber"), int) else parse_floor(d.get("floor")),
            city=d.get("settlementNameHeb"),
            neighborhood=d.get("neighborhood"),
            street=d.get("streetName"),
            house_number=str(d.get("houseNumber")) if d.get("houseNumber") is not None else None,
            property_type=d.get("propertyTypeDescription"),
            year_built=d.get("yearBuilt") if isinstance(d.get("yearBuilt"), int) else None,
            deal_type="second_hand" if deal_type == 2 else "new",
            fetched_at=utcnow(),
            raw=d,
        ))
        added += 1
    return added


def collect_deals_for_location(client: GovmapClient, query: str, months_back: int = 24) -> tuple[list[dict], dict]:
    """Network only: official deals around an address/neighborhood query."""
    stats = {"query": query, "polygons": 0, "deals_seen": 0, "point": None}
    for res in client.autocomplete(query)[:3]:
        pt = GovmapClient.point_of(res)
        if not pt:
            continue
        polys = client.polygons_near(pt, radius=150) or client.polygons_near(pt, radius=400)
        if not polys:
            continue
        ids: list[str] = []
        for p in polys:
            pid = p.get("polygon_id")
            if pid and str(pid) not in ids:
                ids.append(str(pid))
        deals: list[dict] = []
        for pid in ids[:3]:
            deals += client.street_deals(pid, months_back=months_back)
        if ids:
            deals += client.neighborhood_deals(ids[0], months_back=months_back)
        stats.update(point=pt, polygons=len(ids), deals_seen=len(deals))
        return deals, stats
    return [], stats


def to_transactions(deals: list[dict]) -> list[Transaction]:
    """Unsaved Transaction objects (for live, non-persisted views)."""
    out = []
    for d in deals:
        ddate = _parse_date(d.get("dealDate"))
        if not d.get("dealAmount") or ddate is None:
            continue
        rooms = d.get("assetRoomNum")
        out.append(Transaction(
            external_id=str(d.get("objectid")), deal_date=ddate, price=int(float(d["dealAmount"])),
            sqm=float(d["assetArea"]) if d.get("assetArea") else None,
            rooms=float(rooms) if rooms not in (None, "") else None, floor=parse_floor(d.get("floor")),
            city=d.get("settlementNameHeb"), neighborhood=d.get("neighborhood"), street=d.get("streetName"),
            house_number=str(d.get("houseNumber")) if d.get("houseNumber") is not None else None,
            property_type=d.get("propertyTypeDescription"),
        ))
    return out


def fetch_comps_for_location(s: Session, client: GovmapClient, query: str, months_back: int = 24) -> dict:
    deals, stats = collect_deals_for_location(client, query, months_back)
    stats["added"] = store_deals(s, deals)
    return stats
