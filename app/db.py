import logging
import time
from collections.abc import Iterator

from sqlalchemy import create_engine
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


def init_db(attempts: int = 30, delay: float = 2.0) -> None:
    """Create tables, waiting for the database to come up (e.g. in Kubernetes)."""
    log = logging.getLogger("uvicorn.error")
    for attempt in range(1, attempts + 1):
        try:
            Base.metadata.create_all(engine)
            return
        except OperationalError:
            if attempt == attempts:
                raise
            log.warning("Database not ready (attempt %d/%d), retrying in %.0fs", attempt, attempts, delay)
            time.sleep(delay)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
