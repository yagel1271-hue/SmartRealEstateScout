import pytest

from app.database.db import init_db, session_scope


@pytest.fixture()
def db(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    init_db(url)
    return url


@pytest.fixture()
def session(db):
    with session_scope(db) as s:
        yield s
