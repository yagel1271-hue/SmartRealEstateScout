"""Minimal Telegram Bot API client (sendMessage, getUpdates)."""
from __future__ import annotations

import logging

import requests

log = logging.getLogger("scout.telegram")
API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000


class TelegramClient:
    def __init__(self, token: str, chat_id: str | None = None, timeout: float = 30):
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is missing")
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout

    def _call(self, method: str, **params):
        r = requests.post(API.format(token=self.token, method=method), json=params, timeout=self.timeout)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not data.get("ok"):
            # never log the token
            raise RuntimeError(f"Telegram {method} failed: {data.get('description') or r.status_code}")
        return data["result"]

    @staticmethod
    def split(text: str, limit: int = MAX_LEN) -> list[str]:
        parts, cur = [], ""
        for block in text.split("\n\n"):
            if len(cur) + len(block) + 2 > limit and cur:
                parts.append(cur)
                cur = ""
            while len(block) > limit:
                parts.append(block[:limit])
                block = block[limit:]
            cur = f"{cur}\n\n{block}" if cur else block
        if cur:
            parts.append(cur)
        return parts

    def send(self, text: str, chat_id: str | None = None) -> None:
        cid = chat_id or self.chat_id
        if not cid:
            raise ValueError("TELEGRAM_CHAT_ID is missing")
        for part in self.split(text):
            self._call("sendMessage", chat_id=cid, text=part, parse_mode="HTML", disable_web_page_preview=True)

    def updates(self, offset: int | None = None) -> list[dict]:
        params = {"timeout": 0, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", **params)
