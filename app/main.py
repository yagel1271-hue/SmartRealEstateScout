"""Command-line entry point (used by GitHub Actions and locally).

python -m app.main init-db
python -m app.main intake            # CSV inbox + Telegram messages
python -m app.main comps             # fetch official deals near listings
python -m app.main analyze
python -m app.main report [--send] [--scheduled]
python -m app.main daily [--scheduled]   # everything, in order
python -m app.main probe             # check data sources reachability (writes data/probe/)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database.db import get_setting, init_db, session_scope, set_setting
from app.database.models import Alert, Analysis, Listing, ScanHistory, utcnow
from app.logging_setup import setup_logging

log = logging.getLogger("scout")


def _scan(kind: str):
    class _Ctx:
        def __enter__(self):
            with session_scope() as s:
                row = ScanHistory(kind=kind)
                s.add(row)
                s.flush()
                self.id = row.id
            self.stats: dict = {}
            return self

        def __exit__(self, exc_type, exc, tb):
            with session_scope() as s:
                row = s.get(ScanHistory, self.id)
                row.finished_at = utcnow()
                row.stats = self.stats
                row.status = "failed" if exc else self.stats.get("_status", "ok")
                row.error = repr(exc) if exc else self.stats.get("_error")
            return False

    return _Ctx()


def cmd_init_db() -> int:
    init_db()
    print("Database ready")
    return 0


def cmd_intake() -> int:
    from app.collectors.manual_csv import read_inbox_csv
    from app.services.ingest import IngestResult, upsert_listing

    cfg = get_settings()
    with _scan("intake") as scan:
        result = IngestResult()
        with session_scope() as s:
            for p in read_inbox_csv(cfg.inbox_dir / "listings.csv", cfg.cities[0]):
                upsert_listing(s, p, result)
        replies = []
        log.info("Telegram token configured: %s, chat id configured: %s",
                 bool(cfg.telegram_bot_token), bool(cfg.telegram_chat_id))
        if cfg.telegram_bot_token:
            from app.collectors.telegram_intake import process_updates
            from app.notifications.telegram import TelegramClient

            tg = TelegramClient(cfg.telegram_bot_token, cfg.telegram_chat_id)
            with session_scope() as s:
                r2, replies = process_updates(s, tg, cfg.telegram_chat_id, cfg.cities[0])
            for chat_id, text in replies:
                try:
                    tg.send(text, chat_id=chat_id)
                except Exception as exc:  # noqa: BLE001
                    log.warning("reply failed: %s", exc)
            result.new_listings += r2.new_listings
            result.price_drops += r2.price_drops
            result.updated += r2.updated
        scan.stats = {"new": len(result.new_listings), "updated": result.updated,
                      "price_drops": len(result.price_drops), "telegram_messages": len(replies)}
        log.info("Intake: %s", scan.stats)
    return 0


def cmd_comps(max_queries: int = 25) -> int:
    from app.collectors.govmap import GovmapClient, fetch_comps_for_location

    with _scan("comps") as scan:
        client = GovmapClient()
        done, errors = 0, []
        with session_scope() as s:
            fetched: dict = get_setting(s, "comps_fetched", {}) or {}
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
            queries = []
            for l in s.execute(select(Listing).where(Listing.status == "active")).scalars():
                p = l.property
                if p.street:
                    q = f"{p.street} {p.house_number or ''} {p.city}".replace("  ", " ").strip()
                elif p.neighborhood:
                    q = f"{p.neighborhood} {p.city}"
                else:
                    continue
                if fetched.get(q, "") < cutoff and q not in queries:
                    queries.append(q)
        for q in queries[:max_queries]:
            try:
                with session_scope() as s:
                    st = fetch_comps_for_location(s, client, q)
                    fetched[q] = datetime.now(timezone.utc).date().isoformat()
                    set_setting(s, "comps_fetched", dict(fetched))
                done += 1
                log.info("Comps %s", st)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{q}: {exc}")
                log.warning("Comps failed for %s: %s", q, exc)
        scan.stats = {"queries": done, "errors": errors[:5], "pending": max(0, len(queries) - max_queries)}
        if errors:
            scan.stats["_status"] = "partial"
    return 0


def cmd_renewal() -> int:
    from app.collectors.urban_renewal import fetch_city

    cfg = get_settings()
    with _scan("renewal") as scan:
        with session_scope() as s:
            scan.stats = {c: fetch_city(s, c) for c in cfg.cities}
        log.info("Urban renewal compounds: %s", scan.stats)
    return 0


def cmd_rents() -> int:
    """inbox/rents.csv: neighborhood,rooms,sqm,rent,date,url (rental listings you saw / known rents)."""
    import csv
    from datetime import date as _date

    from app.database.db import source_by_code
    from app.database.models import RentalComparable

    cfg = get_settings()
    path = cfg.inbox_dir / "rents.csv"
    if not path.exists():
        return 0
    n = 0
    with session_scope() as s:
        src = source_by_code(s, "manual")
        existing = {(r.neighborhood, r.rooms, r.monthly_rent, r.url) for r in s.query(RentalComparable).all()}
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                try:
                    rent = int(row.get("rent", "").replace(",", ""))
                except ValueError:
                    continue
                rooms = float(row["rooms"]) if row.get("rooms") else None
                key = (row.get("neighborhood") or None, rooms, rent, row.get("url") or None)
                if key in existing:
                    continue
                d = _date.fromisoformat(row["date"]) if row.get("date") else _date.today()
                s.add(RentalComparable(source_id=src.id, city=row.get("city") or cfg.cities[0], neighborhood=key[0],
                                       rooms=rooms, sqm=float(row["sqm"]) if row.get("sqm") else None, monthly_rent=rent,
                                       observed_at=d, origin="user", url=key[3]))
                existing.add(key)
                n += 1
    log.info("Rent comparables added: %d", n)
    return 0


def cmd_analyze() -> int:
    from app.analysis.analyzer import run_analysis

    cfg = get_settings()
    with _scan("analyze") as scan:
        with session_scope() as s:
            res = run_analysis(s, (cfg.budget_min, cfg.budget_max))
            scan.stats = {"analyzed": len(res)}
    return 0


def _already_sent_today(s, cfg) -> bool:
    today_local = datetime.now(cfg.tz).date()
    for a in s.execute(select(Alert).where(Alert.kind == "daily_report", Alert.ok.is_(True))).scalars():
        if a.sent_at.replace(tzinfo=timezone.utc).astimezone(cfg.tz).date() == today_local:
            return True
    return False


def cmd_report(send: bool, scheduled: bool) -> int:
    from app.notifications.telegram import TelegramClient
    from app.services.report import build_daily_report

    cfg = get_settings()
    now_local = datetime.now(cfg.tz)
    with session_scope() as s:
        if scheduled:
            hh, mm = map(int, cfg.daily_report_time.split(":"))
            target = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if not (target - timedelta(minutes=15) <= now_local <= target + timedelta(hours=3)):
                log.info("Not report time (%s local) - skipping send", now_local.strftime("%H:%M"))
                return 0
            if _already_sent_today(s, cfg):
                log.info("Daily report already sent today - skipping")
                return 0
        text = build_daily_report(s, now_local.replace(tzinfo=None), cfg.report_max_items, "(שעון ישראל)")
        if not send:
            print(text)
            return 0
        if not cfg.telegram_configured:
            log.warning("Telegram not configured - report printed only")
            print(text)
            return 0
        ok, err = True, None
        try:
            TelegramClient(cfg.telegram_bot_token, cfg.telegram_chat_id).send(text)
        except Exception as exc:  # noqa: BLE001
            ok, err = False, str(exc)
            log.error("Report send failed: %s", exc)
        s.add(Alert(kind="daily_report", ok=ok, message=text if ok else err))
    return 0 if ok else 1


def cmd_instant_alerts() -> int:
    from app.notifications.telegram import TelegramClient
    from app.services.report import listing_block

    cfg = get_settings()
    if not cfg.telegram_configured:
        return 0
    with session_scope() as s:
        alerted = {a.listing_id for a in s.execute(select(Alert).where(Alert.kind == "instant")).scalars()}
        hits = [a for a in s.execute(select(Analysis).where(Analysis.is_latest.is_(True))).scalars()
                if (a.score or 0) >= cfg.instant_alert_score and a.listing_id not in alerted]
        if not hits:
            return 0
        tg = TelegramClient(cfg.telegram_bot_token, cfg.telegram_chat_id)
        for a in hits:
            l = s.get(Listing, a.listing_id)
            text = "🚨 <b>הזדמנות חדשה מעל סף הציון</b>\n\n" + listing_block(l, a)
            try:
                tg.send(text)
                s.add(Alert(kind="instant", listing_id=l.id, ok=True, message=text))
            except Exception as exc:  # noqa: BLE001
                log.error("Instant alert failed: %s", exc)
    return 0


def cmd_daily(scheduled: bool) -> int:
    init_db()
    rc = 0
    for step in (cmd_intake, cmd_rents, cmd_renewal, cmd_comps, cmd_analyze, cmd_instant_alerts):
        try:
            step()
        except Exception as exc:  # noqa: BLE001 - one failing step must not block the report
            log.exception("Step %s failed: %s", step.__name__, exc)
            rc = 1
    rc = cmd_report(send=True, scheduled=scheduled) or rc
    return rc


def cmd_probe() -> int:
    from app.services.probe import run_probe

    cfg = get_settings()
    out = cfg.data_dir / "probe"
    report = run_probe(out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    cfg = get_settings()
    setup_logging(cfg.logs_dir, cfg.log_level)
    ap = argparse.ArgumentParser(prog="scout")
    ap.add_argument("command", choices=["init-db", "intake", "rents", "renewal", "comps", "analyze", "report", "alerts", "daily", "probe"])
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--scheduled", action="store_true")
    args = ap.parse_args(argv)
    problems = cfg.validate()
    if problems:
        print("Settings problems:", *problems, sep="\n  - ")
        return 2
    if args.command not in ("init-db", "probe"):
        init_db()
    return {
        "init-db": cmd_init_db,
        "intake": cmd_intake,
        "rents": cmd_rents,
        "renewal": cmd_renewal,
        "comps": cmd_comps,
        "analyze": cmd_analyze,
        "report": lambda: cmd_report(args.send, args.scheduled),
        "alerts": cmd_instant_alerts,
        "daily": lambda: cmd_daily(args.scheduled),
        "probe": cmd_probe,
    }[args.command]()


if __name__ == "__main__":
    sys.exit(main())
