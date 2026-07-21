"""GET /api/admin/stats — the usage dashboard (PLAN.md section 8).

The in-app version of ``scripts/analytics.py``: who is using the app, how much,
how recently, and what they searched for. Admin-only via ``require_admin``.

Two things this deliberately does that a plain GROUP BY would not:

  * **Everyone in ACCESS_TOKENS is listed, including people with zero events.**
    The main question this page answers is "has <person> ever used this?", and a
    GROUP BY over the events table can only show people who already have. A
    never-used token has to appear as an explicit "never" row.
  * **Share detection.** One token seen from several ip_hash values means the
    link was forwarded — the token is the analytics user id, so a shared link
    silently merges two people's behaviour into one identity.

All SQL is SQLAlchemy core so it runs on sqlite (local) and postgres (Railway)
unchanged. Every query is wrapped: analytics must never take the page down.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select

from backend import db
from backend.auth import TOKENS, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Events that represent a click on a search result — the relevance/eval pool.
CLICK_TYPES = ("expand_holding", "open_decision", "download_pdf")

# Rows in the recent-activity feed and the top-searches list.
RECENT_LIMIT = 40
TOP_SEARCH_LIMIT = 20
# Days of history in the activity chart.
ACTIVITY_DAYS = 60


def _iso(value):
    """Datetime -> ISO string, passing through None and anything already text."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _events_table():
    """The events Table, or None when the store never initialised."""
    return getattr(db, "events", None)


@router.get("/stats")
def get_stats(_token: str = Depends(require_admin)):
    ev = _events_table()
    if ev is None:  # pragma: no cover - defensive
        return {"ok": False, "error": "events table unavailable", "people": []}

    day = func.date(ev.c.ts)

    try:
        with db.engine.connect() as conn:
            total, first_ts, last_ts = conn.execute(
                select(func.count(), func.min(ev.c.ts), func.max(ev.c.ts))
            ).one()

            # Per-token aggregates, merged onto the full roster below.
            agg = {
                row.user_token: row
                for row in conn.execute(
                    select(
                        ev.c.user_token.label("user_token"),
                        func.count().label("events"),
                        func.count(distinct(ev.c.session_id)).label("sessions"),
                        func.count(distinct(day)).label("active_days"),
                        func.count(distinct(ev.c.ip_hash)).label("ips"),
                        func.min(ev.c.ts).label("first_seen"),
                        func.max(ev.c.ts).label("last_seen"),
                    ).group_by(ev.c.user_token)
                )
            }

            by_type = [
                {"event_type": t, "count": n}
                for t, n in conn.execute(
                    select(ev.c.event_type, func.count())
                    .group_by(ev.c.event_type)
                    .order_by(func.count().desc())
                )
            ]

            top_searches = [
                {"query": q, "count": n, "users": u}
                for q, n, u in conn.execute(
                    select(
                        ev.c.query,
                        func.count(),
                        func.count(distinct(ev.c.user_token)),
                    )
                    .where(ev.c.event_type == "search")
                    .where(ev.c.query.isnot(None))
                    .where(ev.c.query != "")
                    .group_by(ev.c.query)
                    .order_by(func.count().desc())
                    .limit(TOP_SEARCH_LIMIT)
                )
            ]

            n_searches = conn.execute(
                select(func.count()).where(ev.c.event_type == "search")
            ).scalar_one()
            n_clicks, avg_rank = conn.execute(
                select(func.count(), func.avg(ev.c.rank)).where(
                    ev.c.event_type.in_(CLICK_TYPES)
                )
            ).one()

            counts = {
                str(d): int(n)
                for d, n in conn.execute(
                    select(day, func.count())
                    .group_by(day)
                    .order_by(day.desc())
                    .limit(ACTIVITY_DAYS)
                )
            }

            recent = [
                {
                    "ts": _iso(r.ts),
                    "user": TOKENS.get(r.user_token) or r.user_token or "(anonymous)",
                    "event_type": r.event_type,
                    "what": r.query or r.target_id or "",
                    "referrer": r.referrer,
                }
                for r in conn.execute(
                    select(
                        ev.c.ts,
                        ev.c.user_token,
                        ev.c.event_type,
                        ev.c.query,
                        ev.c.target_id,
                        ev.c.referrer,
                    )
                    .order_by(ev.c.ts.desc())
                    .limit(RECENT_LIMIT)
                )
            ]
    except Exception:
        logger.exception("admin stats query failed")
        return {"ok": False, "error": "stats query failed", "people": []}

    # Zero-fill every day in the window. Without this the chart only emits days
    # that HAVE events, so idle stretches vanish and adjacent bars imply
    # continuous use — on a page about *when* people used the app that reads as
    # the opposite of the truth.
    today = datetime.now(timezone.utc).date()
    activity = [
        {"day": (d := (today - timedelta(days=offset))).isoformat(),
         "count": counts.get(d.isoformat(), 0)}
        for offset in range(ACTIVITY_DAYS - 1, -1, -1)
    ]

    # Full roster: every known token, whether or not it has any events. Sorted
    # most-active first, so never-used people sink to the bottom.
    people = []
    for tok, name in TOKENS.items():
        row = agg.get(tok)
        people.append(
            {
                "name": name,
                "events": int(row.events) if row else 0,
                "sessions": int(row.sessions or 0) if row else 0,
                "active_days": int(row.active_days or 0) if row else 0,
                "distinct_ips": int(row.ips or 0) if row else 0,
                "first_seen": _iso(row.first_seen) if row else None,
                "last_seen": _iso(row.last_seen) if row else None,
                # >1 IP for one token = the link was probably forwarded.
                "shared": bool(row and (row.ips or 0) > 1),
            }
        )
    people.sort(key=lambda p: (-p["events"], p["name"]))

    return {
        "ok": True,
        "total_events": int(total or 0),
        "first_event": _iso(first_ts),
        "last_event": _iso(last_ts),
        "people": people,
        "by_type": by_type,
        "top_searches": top_searches,
        "click_through": {
            "searches": int(n_searches or 0),
            "clicks": int(n_clicks or 0),
            "avg_rank": round(float(avg_rank), 2) if avg_rank is not None else None,
        },
        "activity": activity,
        "recent": recent,
    }
