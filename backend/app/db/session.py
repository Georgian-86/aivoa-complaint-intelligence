"""Engine / session wiring.

SQLite is the zero-setup default so the repository runs immediately after a
clone; Postgres (or MySQL) is selected purely by DATABASE_URL, which is what
docker-compose supplies.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def _engine_kwargs() -> dict:
    kwargs: dict = {"echo": settings.sql_echo, "future": True, "pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        # FastAPI runs handlers in a threadpool; SQLite needs this relaxed.
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs.pop("pool_pre_ping")
    return kwargs


engine = create_engine(settings.database_url, **_engine_kwargs())

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver glue
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
