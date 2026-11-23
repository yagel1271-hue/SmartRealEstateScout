"""Central configuration for Smart Real Estate Scout.

Values are read from the .env file (see .env.example). Secrets such as the
Telegram token live ONLY in .env, never in code. Business defaults below are
starting values; later stages will let you change them from the dashboard
settings screen (stored in the database).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Project root = folder that contains the "app" package
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw.replace(",", ""))
    except ValueError as exc:
        raise ValueError(f"Setting {name} must be a whole number, got: {raw!r}") from exc


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name, "").strip()
    return raw or default


@dataclass(frozen=True)
class Settings:
    # --- Paths ---
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"
    db_path: Path = field(default_factory=lambda: BASE_DIR / "data" / _env_str("DB_FILENAME", "scout.db"))

    # --- Business defaults ---
    cities: tuple[str, ...] = field(
        default_factory=lambda: tuple(c.strip() for c in _env_str("CITIES", "פתח תקווה").split(";") if c.strip())
    )
    budget_min: int = field(default_factory=lambda: _env_int("BUDGET_MIN", 1_000_000))
    budget_max: int = field(default_factory=lambda: _env_int("BUDGET_MAX", 1_800_000))

    # --- Schedule ---
    timezone: str = field(default_factory=lambda: _env_str("TIMEZONE", "Asia/Jerusalem"))
    daily_report_time: str = field(default_factory=lambda: _env_str("DAILY_REPORT_TIME", "08:00"))

    # --- Telegram (secrets: .env only) ---
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "").strip())

    # --- Optional local AI ---
    ollama_enabled: bool = field(default_factory=lambda: _env_str("OLLAMA_ENABLED", "false").lower() == "true")
    ollama_model: str = field(default_factory=lambda: _env_str("OLLAMA_MODEL", ""))

    log_level: str = field(default_factory=lambda: _env_str("LOG_LEVEL", "INFO").upper())

    def validate(self) -> list[str]:
        """Return a list of problems (empty list = all good)."""
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


def get_settings() -> Settings:
    return Settings()
