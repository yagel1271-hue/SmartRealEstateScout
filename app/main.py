"""Command-line entry point.

Usage (from the project folder, with .venv active):
    python -m app.main doctor     # environment check
    python -m app.main config     # show current settings (secrets hidden)
    python -m app.main scan       # daily scan (implemented in later stages)
"""
from __future__ import annotations

import argparse
import sys

from app.config import get_settings
from app.logging_setup import setup_logging
from app.services.doctor import format_report, run_checks


def cmd_doctor() -> int:
    settings = get_settings()
    results = run_checks(settings.base_dir)
    print(format_report(results))
    return 0 if all(r.ok for r in results if r.required) else 1


def cmd_config() -> int:
    s = get_settings()
    print(f"Cities          : {', '.join(s.cities)}")
    print(f"Budget          : {s.budget_min:,} - {s.budget_max:,} ILS")
    print(f"Daily report    : {s.daily_report_time} ({s.timezone})")
    print(f"Database        : {s.db_path}")
    print(f"Telegram        : {'configured' if s.telegram_configured else 'NOT configured (stage 11)'}")
    print(f"Ollama          : {'enabled - ' + s.ollama_model if s.ollama_enabled else 'disabled'}")
    problems = s.validate()
    if problems:
        print("\nSETTINGS PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nSettings OK")
    return 0


def cmd_scan() -> int:
    s = get_settings()
    log = setup_logging(s.logs_dir, s.log_level)
    log.info("Scan requested - collectors are not implemented yet (stage 5).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scout", description="Smart Real Estate Scout")
    parser.add_argument("command", choices=["doctor", "config", "scan"])
    args = parser.parse_args(argv)
    return {"doctor": cmd_doctor, "config": cmd_config, "scan": cmd_scan}[args.command]()


if __name__ == "__main__":
    sys.exit(main())
