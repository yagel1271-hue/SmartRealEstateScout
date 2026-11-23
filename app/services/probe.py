"""Check that official data sources are reachable from the runner.

Writes small raw samples to data/probe/ so the response formats can be
inspected. Only official/public sources are probed - never sites whose
terms forbid automated access.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

UA = "SmartRealEstateScout/1.0 (personal investment research; low volume)"
PT_CODE = 7900  # CBS settlement code of Petah Tikva


def _save(out: Path, name: str, data) -> None:  # noqa: ANN001
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=1) if not isinstance(data, str) else data
    (out / name).write_text(text[:200_000], encoding="utf-8")


def _try(report: dict, name: str, fn) -> None:  # noqa: ANN001
    t0 = time.time()
    try:
        info = fn()
        report[name] = {"ok": True, "secs": round(time.time() - t0, 1), **(info or {})}
    except Exception as exc:  # noqa: BLE001
        report[name] = {"ok": False, "secs": round(time.time() - t0, 1), "error": f"{type(exc).__name__}: {exc}"[:300]}


def run_probe(out: Path) -> dict:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    report: dict = {}

    def govmap():
        r = s.post("https://www.govmap.gov.il/api/search-service/autocomplete",
                   json={"searchText": "רוטשילד 57 פתח תקווה", "language": "he", "isAccurate": False, "maxResults": 3},
                   timeout=30)
        r.raise_for_status()
        ac = r.json()
        _save(out, "govmap_autocomplete.json", ac)
        res = (ac.get("results") or [])
        shape = res[0].get("shape") if res else None
        info = {"autocomplete_results": len(res), "shape": shape}
        if shape and shape.startswith("POINT("):
            x, y = shape[6:-1].split()
            r2 = s.get(f"https://www.govmap.gov.il/api/real-estate/deals/{x},{y}/150", timeout=30)
            r2.raise_for_status()
            polys = r2.json()
            _save(out, "govmap_polygons.json", polys)
            info["polygons"] = len(polys) if isinstance(polys, list) else str(type(polys))
            if isinstance(polys, list) and polys:
                pid = polys[0].get("polygon_id")
                r3 = s.get(f"https://www.govmap.gov.il/api/real-estate/street-deals/{pid}",
                           params={"limit": 20, "dealType": 2}, timeout=30)
                r3.raise_for_status()
                deals = r3.json()
                _save(out, "govmap_street_deals.json", deals)
                data = deals.get("data", deals) if isinstance(deals, dict) else deals
                info["street_deals"] = len(data) if isinstance(data, list) else str(type(data))
                if isinstance(data, list) and data:
                    info["deal_keys"] = sorted(data[0].keys())
        return info

    def nadlan_index(kind: str):
        def _f():
            url = f"https://data.nadlan.gov.il/api/pages/settlement/{kind}/{PT_CODE}.json"
            r = s.get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
            _save(out, f"nadlan_{kind}_{PT_CODE}.json", data)
            return {"url": url, "top_keys": sorted(data.keys())[:40] if isinstance(data, dict) else str(type(data))}
        return _f

    def datagov_renewal():
        r = s.get("https://data.gov.il/api/3/action/package_search",
                  params={"q": "התחדשות עירונית", "rows": 10}, timeout=30)
        r.raise_for_status()
        data = r.json()
        pkgs = [
            {"name": p.get("name"), "title": p.get("title"),
             "resources": [{"id": x.get("id"), "name": x.get("name"), "format": x.get("format"), "url": x.get("url")}
                           for x in p.get("resources", [])][:6]}
            for p in data.get("result", {}).get("results", [])
        ]
        _save(out, "datagov_renewal_packages.json", pkgs)
        return {"packages": [p["title"] for p in pkgs]}

    def renewal_rows():
        r = s.get("https://data.gov.il/api/3/action/datastore_search",
                  params={"resource_id": "f65a0daf-f737-49c5-9424-d378d52104f5", "q": "פתח תקווה", "limit": 200}, timeout=30)
        r.raise_for_status()
        res = r.json().get("result", {})
        _save(out, "renewal_petah_tikva.json", res)
        return {"total": res.get("total"), "fields": [f.get("id") for f in res.get("fields", [])]}

    def datagov_search():
        found = {}
        for q in ["עסקאות נדל\"ן", "מכירת דירות", "שכר דירה", "מחירי דירות", "נדל\"ן", "real estate transactions"]:
            r = s.get("https://data.gov.il/api/3/action/package_search", params={"q": q, "rows": 8}, timeout=30)
            r.raise_for_status()
            found[q] = [
                {"name": p.get("name"), "title": p.get("title"), "org": (p.get("organization") or {}).get("title"),
                 "resources": [{"id": x.get("id"), "name": x.get("name"), "format": x.get("format"),
                                "datastore": x.get("datastore_active")} for x in p.get("resources", [])][:5]}
                for p in r.json().get("result", {}).get("results", [])
            ]
        _save(out, "datagov_search.json", found)
        return {q: [p["title"] for p in v] for q, v in found.items()}

    def cbs_api():
        r = s.get("https://apis.cbs.gov.il/series/catalog/level", params={"id": 1, "format": "json", "download": "false"},
                  timeout=30)
        r.raise_for_status()
        _save(out, "cbs_catalog.json", r.json())
        return {"status": r.status_code}

    _try(report, "datagov_renewal_rows", renewal_rows)
    _try(report, "datagov_search", datagov_search)
    _try(report, "cbs_api", cbs_api)
    _try(report, "govmap_deals", govmap)
    _try(report, "nadlan_index_buy", nadlan_index("buy"))
    _try(report, "nadlan_index_rent", nadlan_index("rent"))
    _try(report, "datagov_urban_renewal", datagov_renewal)
    _save(out, "summary.json", report)
    return report
