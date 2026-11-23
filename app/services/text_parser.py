"""Extract listing fields from free text the user sends (Hebrew/English).

Deterministic regex only - no AI. Everything extracted is marked origin
"listing" (it came from the ad text); nothing is guessed. Fields that are
not found stay None.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.services.normalize import clean, norm_city, parse_floor

YAD2_RE = re.compile(r"yad2\.co\.il/(?:realestate/)?item/(?:[\w-]+/)?([A-Za-z0-9]+)")
MADLAN_RE = re.compile(r"madlan\.co\.il/listings/([A-Za-z0-9]+)")
URL_RE = re.compile(r"https?://\S+")

KNOWN_NEIGHBORHOODS = [
    "כפר גנים א", "כפר גנים ב", "כפר גנים ג", "כפר גנים", "הדר גנים", "הדר המושבות", "נווה גן",
    "נווה עוז", "פסגת הדר", "אם המושבות", "עין גנים", "מחנה יהודה", "שעריה", "רמת ורבר",
    "רמת ורד", "קרית מטלון", "קריית מטלון", "קרית אליעזר פרי", "קריית אליעזר פרי", "לב המושבה",
    "המרכז השקט", "מרכז העיר", "בר יהודה", "כפר אברהם", "שיפר", "נווה דקלים", "קרול",
    "סגולה", "קרית אריה", "קריית אריה", "קרית הרב סלומון", "בלינסון", "תקומה", "שמחה הולצברג",
    "צמרת גנים", "גני הדר", "נווה כיר", "רמת סיב", "אחדות", "בת גנים", "נוה עוז", "קרית חזני",
]


@dataclass
class ParsedListing:
    source_code: str
    external_id: str
    url: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    street: str | None = None
    house_number: str | None = None
    asking_price: int | None = None
    rooms: float | None = None
    sqm: float | None = None
    floor: int | None = None
    building_floors: int | None = None
    elevator: bool | None = None
    parking: bool | None = None
    balcony: bool | None = None
    mamad: bool | None = None
    condition: str | None = None
    known_rent: int | None = None
    year_built: int | None = None
    description: str | None = None
    found_fields: list[str] = field(default_factory=list)


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _price(text: str) -> int | None:
    # "1.65 מיליון" / "1.65M"
    m = re.search(r"(\d(?:[.,]\d{1,3})?)\s*(?:מיליון|מליון|מ'|M\b|m\b)", text)
    if m:
        v = float(m.group(1).replace(",", "."))
        if 0.3 <= v <= 20:
            return int(round(v * 1_000_000))
    # "1,650,000" with ₪ / ש"ח / NIS nearby, or any 7-digit number in range
    candidates = re.findall(r"(?<![\d,.\-])(\d{1,2}[,.]\d{3}[,.]\d{3}|\d{6,8})(?![\d,.]*\d)", text)
    for c in candidates:
        v = int(re.sub(r"[^\d]", "", c))
        if 300_000 <= v <= 20_000_000:
            return v
    return None


def _rent(text: str) -> int | None:
    m = re.search(r"(?:שכירות|שכ\"ד|שכר דירה|מושכרת ב|rent)[^\d]{0,15}(\d{1,2}[,.]?\d{3})", text)
    if m:
        v = int(re.sub(r"[^\d]", "", m.group(1)))
        if 1_500 <= v <= 30_000:
            return v
    return None


def _flag(text: str, positive: list[str], negative: list[str]) -> bool | None:
    for n in negative:
        if n in text:
            return False
    for p in positive:
        if p in text:
            return True
    return None


def parse_listing_text(raw: str, default_city: str | None = None) -> ParsedListing:
    text = clean(raw)
    url_m = URL_RE.search(text)
    url = url_m.group().rstrip(").,") if url_m else None

    source, ext = "telegram", None
    if m := YAD2_RE.search(text):
        source, ext = "yad2", m.group(1)
    elif m := MADLAN_RE.search(text):
        source, ext = "madlan", m.group(1)
    if not ext:
        ext = "t-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

    body = URL_RE.sub(" ", text)
    p = ParsedListing(source_code=source, external_id=ext, url=url, description=body.strip() or None)

    def found(name: str) -> None:
        p.found_fields.append(name)

    if (v := _price(body)) is not None:
        p.asking_price = v
        found("asking_price")
    if m := re.search(r"(\d(?:\.5)?)\s*(?:חדרים|חד'|חד׳|חדר|rooms?\b)", body):
        p.rooms = _num(m.group(1))
        found("rooms")
    if m := re.search(r"(\d{2,3})\s*(?:מ\"ר|מ'ר|מטר|מ״ר|sqm|m2|מר\b)", body):
        p.sqm = _num(m.group(1))
        found("sqm")
    if m := re.search(r"קומה\s*(קרקע|\d{1,2})(?:\s*(?:מתוך|/)\s*(\d{1,2}))?", body):
        p.floor = parse_floor(m.group(1))
        if m.group(2):
            p.building_floors = int(m.group(2))
        found("floor")
    if m := re.search(r"(?:רחוב|רח'|ברחוב|שדרות|שד')\s*([א-ת\"' ]{2,25}?)\s+(\d{1,3}[א-ת]?)\b", body):
        p.street, p.house_number = m.group(1).strip(), m.group(2)
        found("street")
    for n in KNOWN_NEIGHBORHOODS:
        if n in body:
            p.neighborhood = n
            found("neighborhood")
            break
    if "פתח תקו" in body or "פ\"ת" in body:
        p.city = "פתח תקווה"
    else:
        p.city = norm_city(default_city)
    if m := re.search(r"(?:שנת בנייה|נבנה ב|בנוי מ)\D{0,5}(19\d{2}|20[0-3]\d)", body):
        p.year_built = int(m.group(1))
        found("year_built")

    p.elevator = _flag(body, ["מעלית"], ["ללא מעלית", "אין מעלית", "בלי מעלית"])
    p.parking = _flag(body, ["חניה", "חנייה"], ["ללא חניה", "אין חניה", "ללא חנייה", "אין חנייה"])
    p.balcony = _flag(body, ["מרפסת"], ["ללא מרפסת", "אין מרפסת"])
    p.mamad = _flag(body, ["ממ\"ד", "ממד", "ממ״ד"], ["ללא ממ\"ד", "אין ממ\"ד", "ללא ממד", "אין ממד"])
    if any(w in body for w in ("דרוש שיפוץ", "דורשת שיפוץ", "לשיפוץ", "טעונה שיפוץ")):
        p.condition = "needs_renovation"
    elif any(w in body for w in ("משופצת", "שופצה", "לאחר שיפוץ")):
        p.condition = "renovated"
    elif any(w in body for w in ("חדשה מקבלן", "חדש מקבלן")):
        p.condition = "new"
    for f in ("elevator", "parking", "balcony", "mamad", "condition"):
        if getattr(p, f) is not None:
            found(f)
    if (r := _rent(body)) is not None:
        p.known_rent = r
        found("known_rent")
    return p
