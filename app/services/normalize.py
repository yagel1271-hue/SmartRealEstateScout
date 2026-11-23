"""Normalization helpers for Hebrew addresses and numbers."""
from __future__ import annotations

import re

_STREET_PREFIXES = ("רחוב ", "רח' ", "רח ", "שד' ", "שדרות ", "שד ", "דרך ")
_QUOTES = str.maketrans({"״": '"', "׳": "'", "`": "'", "”": '"', "“": '"', "’": "'"})

CITY_ALIASES = {
    "פתח תקוה": "פתח תקווה",
    "פ\"ת": "פתח תקווה",
    "פתח-תקווה": "פתח תקווה",
    "petah tikva": "פתח תקווה",
    "petah tiqwa": "פתח תקווה",
}


def clean(text: str | None) -> str:
    if not text:
        return ""
    t = text.translate(_QUOTES)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def norm_city(city: str | None) -> str | None:
    if not city:
        return None
    c = clean(city)
    return CITY_ALIASES.get(c.lower(), CITY_ALIASES.get(c, c))


def norm_street(street: str | None) -> str | None:
    if not street:
        return None
    s = clean(street)
    for p in _STREET_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
    s = s.replace("-", " ").replace('"', "").replace("'", "")
    return re.sub(r"\s+", " ", s).strip() or None


def norm_address(city: str | None, street: str | None, house: str | None) -> str | None:
    st = norm_street(street)
    if not st:
        return None
    parts = [norm_city(city) or "", st, (house or "").strip()]
    return "|".join(parts).lower()


def parse_int(text: str | None) -> int | None:
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


def parse_floor(text: str | int | None) -> int | None:
    if text is None:
        return None
    if isinstance(text, int):
        return text
    t = clean(str(text))
    if any(w in t for w in ("קרקע", "ground", "Ground")):
        return 0
    if "מרתף" in t:
        return -1
    m = re.search(r"-?\d+", t)
    return int(m.group()) if m else None
