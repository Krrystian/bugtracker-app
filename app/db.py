import logging
import time
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = get_settings().sqlalchemy_url()
    if str(url).startswith("sqlite"):
        return create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    return create_engine(url, pool_pre_ping=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Arbitrary key for the PostgreSQL advisory lock guarding schema creation.
_SCHEMA_LOCK_ID = 7_314_202_601


def _create_schema() -> None:
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            # Several replicas may start at once on an empty database; serialize
            # CREATE TYPE/TABLE so they don't race. Released at transaction end.
            conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _SCHEMA_LOCK_ID})
        Base.metadata.create_all(conn)


def init_db(attempts: int = 30, delay: float = 2.0) -> None:
    """Create tables, waiting for the database to come up (e.g. in Kubernetes)."""
    log = logging.getLogger("uvicorn.error")
    for attempt in range(1, attempts + 1):
        try:
            _create_schema()
            return
        except OperationalError:
            if attempt == attempts:
                raise
            log.warning("Database not ready (attempt %d/%d), retrying in %.0fs", attempt, attempts, delay)
            time.sleep(delay)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
