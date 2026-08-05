"""Engine, session factory, and the FastAPI session dependency."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

settings.data_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    # SQLite's default threading check is too strict for FastAPI's threadpool,
    # which may hand the same connection to a different worker thread.
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection, connection_record) -> None:
    """SQLite defaults are wrong for us in two ways worth fixing up front."""
    cursor = dbapi_connection.cursor()
    # Foreign keys are OFF by default in SQLite, so ON DELETE clauses and
    # relationship integrity would silently do nothing.
    cursor.execute("PRAGMA foreign_keys=ON")
    # WAL keeps reads from blocking on the scheduler's background writes.
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
