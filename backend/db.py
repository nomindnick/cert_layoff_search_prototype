"""Analytics event store — SQLAlchemy 2.x core, portable across sqlite and postgres.

One append-only ``events`` table backs product usage, the leakage-free eval
relevance pool, and future training data (see PLAN.md section 8). The engine is
built from ``settings.DATABASE_URL`` (``sqlite:///./events.db`` by default,
``postgresql://...`` on Railway). The JSON columns use SQLAlchemy's generic
``JSON`` type, which maps to ``JSON``/``TEXT`` on sqlite and ``JSON`` on postgres.
"""

from __future__ import annotations

import logging

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    insert,
)

from backend.config import settings

logger = logging.getLogger(__name__)

metadata_obj = MetaData()

# Append-only event log. Column set mirrors PLAN.md section 8.
events = Table(
    "events",
    metadata_obj,
    # BigInteger autoincrement is BIGSERIAL on postgres. SQLite only treats a
    # literal INTEGER PRIMARY KEY as a rowid alias (BIGINT will not
    # autoincrement and leaves id NULL), so use a sqlite-specific Integer
    # variant to get a true rowid alias on sqlite while keeping BIGINT on pg.
    Column(
        "id",
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column("ts", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("user_token", String(255)),
    Column("session_id", String(255)),
    Column("event_type", String(64), nullable=False),
    Column("query", Text),
    Column("query_type", String(32)),
    Column("filters", JSON),
    Column("shown", JSON),
    Column("target_id", String(255)),
    Column("rank", Integer),
    Column("dwell_ms", Integer),
    Column("referrer", Text),
    Column("user_agent", Text),
    Column("ip_hash", String(128)),
)


def _make_engine():
    url = settings.DATABASE_URL
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    # sqlite + a threaded ASGI server needs check_same_thread disabled.
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs.pop("pool_pre_ping", None)
    return create_engine(url, **kwargs)


engine = _make_engine()


def create_all() -> None:
    """Create the events table if it does not yet exist. Idempotent."""
    metadata_obj.create_all(engine)


def insert_event(**fields) -> None:
    """Insert one event row. Only known columns are persisted; unknown keys are
    dropped so the caller can pass a superset without raising."""
    valid = {c.name for c in events.columns}
    row = {k: v for k, v in fields.items() if k in valid and k != "id"}
    with engine.begin() as conn:
        conn.execute(insert(events).values(**row))
