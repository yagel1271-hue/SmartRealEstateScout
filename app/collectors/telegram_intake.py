"""Listings the user sends to the Telegram bot (link and/or ad text).

Only messages from the configured TELEGRAM_CHAT_ID are processed.
Commands:
  /start or /help        - usage
  /sold <id>             - mark listing as sold/removed
  /rent <id> <amount>    - set known monthly rent
  /fav <id>              - add to favorites
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.database.db import get_setting, set_setting
from app.database.models import Favorite, Listing
from app.notifications.telegram import TelegramClient
from app.services.ingest import IngestResult, upsert_listing
from app.services.text_parser import parse_listing_text

log = logging.getLogger("scout.intake")

HELP = (
    "שלח לי מודעה – קישור (יד2/מדלן/תיווך) יחד עם הטקסט שלה, או רק את פרטי הדירה.\n"
    "לדוגמה:\nרחוב אחד העם 61, 3 חדרים, 66 מ\"ר, קומה 3, 1,690,000 ₪\n\n"
    "המערכת לא סורקת אתרים שאוסרים זאת – היא מנתחת רק מה שאתה שולח, מול עסקאות רשמיות.\n"
    "פקודות: /sold מספר · /rent מספר סכום · /fav מספר"
)


def process_updates(s: Session, tg: TelegramClient, allowed_chat_id: str, default_city: str) -> tuple[IngestResult, list[tuple[str, str]]]:
    """Returns ingest result and list of (chat_id, reply_text) to send."""
    offset = get_setting(s, "telegram_offset")
    updates = tg.updates(offset)
    result = IngestResult()
    replies: list[tuple[str, str]] = []
    max_id = offset - 1 if offset else None
    for u in updates:
        max_id = max(max_id or 0, u["update_id"])
        msg = u.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id", ""))
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if not text:
            continue
        if chat_id != str(allowed_chat_id):
            if text.startswith("/start"):
                replies.append((chat_id, f"מזהה הצ'אט שלך: {chat_id}\nיש להגדיר אותו כ-TELEGRAM_CHAT_ID ב-GitHub Secrets."))
            continue
        if text.startswith(("/start", "/help")):
            replies.append((chat_id, HELP))
            continue
        parts = text.split()
        if parts[0] in ("/sold", "/rent", "/fav") and len(parts) >= 2 and parts[1].isdigit():
            l = s.get(Listing, int(parts[1]))
            if not l:
                replies.append((chat_id, f"לא נמצאה מודעה {parts[1]}"))
                continue
            if parts[0] == "/sold":
                l.status = "sold"
                replies.append((chat_id, f"מודעה {l.id} סומנה כנמכרה/הוסרה"))
            elif parts[0] == "/rent" and len(parts) >= 3 and parts[2].replace(",", "").isdigit():
                l.known_rent = int(parts[2].replace(",", ""))
                l.field_origin = {**(l.field_origin or {}), "known_rent": "user"}
                replies.append((chat_id, f"שכ\"ד {l.known_rent:,} ₪ נשמר למודעה {l.id}"))
            elif parts[0] == "/fav":
                if not s.query(Favorite).filter_by(listing_id=l.id).first():
                    s.add(Favorite(listing_id=l.id))
                replies.append((chat_id, f"מודעה {l.id} נוספה למועדפים"))
            continue
        parsed = parse_listing_text(text, default_city=default_city)
        if not parsed.found_fields and not parsed.url:
            replies.append((chat_id, "לא זיהיתי פרטי מודעה. שלח קישור ו/או מחיר, חדרים, מ\"ר וכתובת."))
            continue
        listing = upsert_listing(s, parsed, result)
        missing = [he for f, he in [("asking_price", "מחיר"), ("rooms", "חדרים"), ("sqm", "מ\"ר"),
                                    ("street", "רחוב"), ("floor", "קומה")] if f not in parsed.found_fields]
        msg_txt = f"נקלט ✔ מודעה #{listing.id}"
        if missing:
            msg_txt += "\nחסר: " + ", ".join(missing) + " – אפשר לשלוח שוב עם הפרטים (באותו קישור) כדי להשלים."
        msg_txt += "\nהניתוח יופיע בדוח הבא ובדשבורד."
        replies.append((chat_id, msg_txt))
    if max_id is not None:
        set_setting(s, "telegram_offset", max_id + 1)
    return result, replies
