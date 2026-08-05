from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


@pytest.fixture()
def engine() -> Engine:
    """A throwaway in-memory database with the real schema."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        # An in-memory SQLite database lives inside a single connection, and
        # TestClient runs the app on another thread. Without StaticPool that
        # thread would open a second, empty database.
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_connection, connection_record):
        # Mirror the app's PRAGMA so constraint behaviour matches production.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine: Engine) -> Session:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        yield s


@pytest.fixture(autouse=True)
def fake_prices():
    """Install a fake price provider for every test.

    Autouse and unconditional: a test that accidentally reaches the real
    yfinance would be slow and would fail whenever the market or the scraper
    misbehaves. Tests that care about prices script this fixture.
    """
    from app.services import prices
    from tests.fake_provider import FakeProvider

    original = prices.get_provider()
    fake = FakeProvider()
    prices.set_provider(fake)
    yield fake
    prices.set_provider(original)


@pytest.fixture()
def client(session: Session):
    """A TestClient wired to the in-memory test session, with seed data loaded.

    Deliberately NOT used as a context manager: that would run the app's
    lifespan, which seeds the real on-disk database. We seed the in-memory one
    here instead, so tests never touch `data/finance.db`.
    """
    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import app
    from app.seed import run_seed

    run_seed(session)

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()
