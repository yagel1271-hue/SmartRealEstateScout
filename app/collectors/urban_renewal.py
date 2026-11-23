"""Official urban-renewal compounds (Government Authority for Urban Renewal) via data.gov.il.

Status is stored EXACTLY as published. Matching a listing to a compound is
by street/neighborhood name inside the compound name - an indication only,
to be verified in the linked plan (mavat).
"""
from __future__ import annotations

import json
import logging
import re

import requests
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.database.db import source_by_code
from app.database.models import Source, UrbanRenewal, utcnow

log = logging.getLogger("scout.renewal")
RESOURCE_ID = "f65a0daf-f737-49c5-9424-d378d52104f5"
API = "https://data.gov.il/api/3/action/datastore_search"
CITY_CODES = {"פתח תקווה": 7900}
UA = "SmartRealEstateScout/1.0 (personal investment research; low volume)"


def ensure_source(s: Session) -> Source:
    try:
        return source_by_code(s, "datagov_renewal")
    except KeyError:
        src = Source(code="datagov_renewal", name="הרשות להתחדשות עירונית – מתחמים (data.gov.il)", kind="renewal",
                     url="https://data.gov.il/dataset/urban_renewal", automated=True, reliability="official",
                     terms_note="מאגר ממשלתי פתוח")
        s.add(src)
        s.flush()
        return src


def _clean(v) -> str:  # noqa: ANN001
    return re.sub(r"\s+", " ", str(v or "").replace("\xa0", " ")).strip()


def _int(v) -> int | None:  # noqa: ANN001
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def name_tokens(name: str) -> list[str]:
    parts = re.split(r"[-/+,()]|\s{2,}", name)
    out = []
    for p in parts:
        p = re.sub(r"\b\d+\b", "", p).replace("מתחמים", "").replace("מתחם", "").strip()
        if len(p) >= 3:
            out.append(p)
    return out


def store_records(s: Session, city: str, records: list[dict]) -> int:
    src = ensure_source(s)
    s.execute(delete(UrbanRenewal).where(UrbanRenewal.city == city, UrbanRenewal.source_id == src.id))
    for r in records:
        name = _clean(r.get("ShemMitcham"))
        if not name:
            continue
        s.add(UrbanRenewal(
            source_id=src.id, city=city, name=name, track=_clean(r.get("Maslul")) or None,
            status=_clean(r.get("Status")) or "לא צוין", plan_number=_clean(r.get("MisparTochnit")) or None,
            streets=name_tokens(name), units_existing=_int(r.get("YachadKayam")),
            units_planned=_int(r.get("YachadTosafti")), source_url=_clean(r.get("KishurLatar")) or None,
            fetched_at=utcnow(),
        ))
    return len(records)


def fetch_city(s: Session, city: str) -> int:
    code = CITY_CODES.get(city)
    if code is None:
        log.warning("No settlement code for %s", city)
        return 0
    r = requests.get(API, params={"resource_id": RESOURCE_ID, "filters": json.dumps({"SemelYeshuv": code}), "limit": 1000},
                     headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    records = r.json().get("result", {}).get("records", [])
    return store_records(s, city, records)
