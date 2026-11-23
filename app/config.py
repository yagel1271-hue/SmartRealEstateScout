"""Central configuration.

Runs in the cloud (GitHub Actions + Streamlit Community Cloud).
Secrets (Telegram token) come from environment variables, which GitHub
Actions fills from the repository's encrypted Secrets. Nothing secret is
stored in code or in the repository.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # .env is optional (only for local runs)
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")


def _file_settings() -> dict:
    """config/settings.json - editable on github.com without touching code."""
    import json

    path = BASE_DIR / "config" / "settings.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_FILE_KEYS = {
    "BUDGET_MIN": "budget_min", "BUDGET_MAX": "budget_max", "DAILY_REPORT_TIME": "daily_report_time",
    "INSTANT_ALERT_SCORE": "instant_alert_score", "REPORT_MAX_ITEMS": "report_max_items",
}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw and name in _FILE_KEYS and _FILE_KEYS[name] in _file_settings():
        return int(_file_settings()[_FILE_KEYS[name]])
    if not raw:
        return default
    try:
        return int(raw.replace(",", ""))
    except ValueError as exc:
        raise ValueError(f"Setting {name} must be a whole number, got: {raw!r}") from exc


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name, "").strip()
    if not raw and name in _FILE_KEYS and _FILE_KEYS[name] in _file_settings():
        return str(_file_settings()[_FILE_KEYS[name]])
    if not raw and name == "CITIES" and _file_settings().get("cities"):
        return ";".join(_file_settings()["cities"])
    return raw or default


def score_weights() -> dict[str, float] | None:
    w = _file_settings().get("score_weights")
    return {k: float(v) for k, v in w.items()} if isinstance(w, dict) else None


@dataclass(frozen=True)
class Settings:
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    inbox_dir: Path = BASE_DIR / "inbox"
    logs_dir: Path = BASE_DIR / "logs"
    db_url: str = field(
        default_factory=lambda: _env_str("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'data' / 'scout.db').as_posix()}")
    )

    cities: tuple[str, ...] = field(
        default_factory=lambda: tuple(c.strip() for c in _env_str("CITIES", "פתח תקווה").split(";") if c.strip())
    )
    budget_min: int = field(default_factory=lambda: _env_int("BUDGET_MIN", 1_000_000))
    budget_max: int = field(default_factory=lambda: _env_int("BUDGET_MAX", 1_800_000))

    timezone: str = field(default_factory=lambda: _env_str("TIMEZONE", "Asia/Jerusalem"))
    daily_report_time: str = field(default_factory=lambda: _env_str("DAILY_REPORT_TIME", "08:00"))
    instant_alert_score: int = field(default_factory=lambda: _env_int("INSTANT_ALERT_SCORE", 80))
    report_max_items: int = field(default_factory=lambda: _env_int("REPORT_MAX_ITEMS", 5))

    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "").strip())

    log_level: str = field(default_factory=lambda: _env_str("LOG_LEVEL", "INFO").upper())

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.budget_min <= 0:
            problems.append("BUDGET_MIN must be positive")
        if self.budget_max < self.budget_min:
            problems.append("BUDGET_MAX must be >= BUDGET_MIN")
        if not self.cities:
            problems.append("CITIES must contain at least one city")
        try:
            ZoneInfo(self.timezone)
        except Exception:
            problems.append(f"Unknown TIMEZONE: {self.timezone}")
        parts = self.daily_report_time.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts) or not (
            0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59
        ):
            problems.append(f"DAILY_REPORT_TIME must be HH:MM, got {self.daily_report_time!r}")
        return problems

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def get_settings() -> Settings:
    return Settings()
