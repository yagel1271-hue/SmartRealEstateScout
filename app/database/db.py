"""Engine, sessions, initial data."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.database.models import Base, Setting, Source

_engines: dict[str, Engine] = {}

SOURCES = [
    dict(code="govmap_deals", name="GovMap – עסקאות נדל\"ן (רשות המסים)", kind="transactions",
         url="https://www.govmap.gov.il", automated=True, reliability="official",
         terms_note="ממשק ציבורי חינמי של עסקאות שנרשמו"),
    dict(code="nadlan_gov_index", name="מידע נדל\"ן – מדדי מחיר ושכירות לישוב", kind="index",
         url="https://www.nadlan.gov.il", automated=True, reliability="official",
         terms_note="נתונים ממשלתיים פתוחים"),
    dict(code="manual", name="הזנה ידנית / קובץ", kind="manual", url=None, automated=False,
         reliability="reported", terms_note="נתונים שהמשתמש הזין"),
    dict(code="telegram", name="מודעה שנשלחה לבוט Telegram", kind="manual", url=None, automated=False,
         reliability="reported", terms_note="טקסט/קישור שהמשתמש העביר לבוט"),
    dict(code="yad2", name="יד2 (קישור שהמשתמש שמר)", kind="listing", url="https://www.yad2.co.il",
         automated=False, reliability="reported",
         terms_note="תקנון יד2 אוסר איסוף אוטומטי – המערכת לא סורקת את האתר; רק קישורים/טקסט שהמשתמש שלח"),
    dict(code="madlan", name="מדלן (קישור שהמשתמש שמר)", kind="listing", url="https://www.madlan.co.il",
         automated=False, reliability="reported",
         terms_note="לא נסרק אוטומטית; רק קישורים/טקסט שהמשתמש שלח"),
]


def get_engine(url: str | None = None) -> Engine:
    url = url or get_settings().db_url
    if url not in _engines:
        if url.startswith("sqlite:///"):
            from pathlib import Path

            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, future=True)
        if url.startswith("sqlite"):
            @event.listens_for(engine, "connect")
            def _fk_on(dbapi_conn, _):  # noqa: ANN001
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
        _engines[url] = engine
    return _engines[url]


def init_db(url: str | None = None) -> Engine:
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        existing = {c for (c,) in s.execute(select(Source.code))}
        for src in SOURCES:
            if src["code"] not in existing:
                s.add(Source(**src))
        s.commit()
    return engine


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    factory = sessionmaker(bind=get_engine(url), expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def source_by_code(s: Session, code: str) -> Source:
    src = s.execute(select(Source).where(Source.code == code)).scalar_one_or_none()
    if src is None:
        raise KeyError(f"Unknown source {code}; run init-db")
    return src


def get_setting(s: Session, key: str, default=None):  # noqa: ANN001
    row = s.get(Setting, key)
    return row.value if row else default


def set_setting(s: Session, key: str, value) -> None:  # noqa: ANN001
    row = s.get(Setting, key)
    if row:
        row.value = value
    else:
        s.add(Setting(key=key, value=value))
