"""Analytics event recording (PLAN.md section 8).

``record_event`` enriches a client-supplied ``EventIn`` with server-side signal
(the auth token as user id, a hashed client IP for share-detection, and the
user agent) and appends it to the events table. It is fire-and-forget: any
failure is logged and swallowed so analytics can never break a request.
"""

from __future__ import annotations

import hashlib
import logging

from fastapi import Request

from backend import db
from backend.auth import current_token
from backend.models import EventIn

logger = logging.getLogger(__name__)

# Salts the IP hash so stored values are not trivially reversible. The point is
# share detection (one token across many IPs), not identifying individuals.
_IP_SALT = "cert_layoff_search_prototype:v1"


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP: honor X-Forwarded-For (Railway sits behind a
    proxy), else the direct peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256((_IP_SALT + ip).encode("utf-8")).hexdigest()


def record_event(request: Request, event: EventIn) -> None:
    """Persist one analytics event. Never raises to the caller."""
    try:
        # ``shown`` and ``filters`` are stored as JSON; normalize pydantic
        # sub-models / None to plain JSON-able values.
        shown = event.shown
        filters = event.filters
        if shown is not None and not isinstance(shown, (list, dict)):
            shown = None

        db.insert_event(
            user_token=current_token(request),
            session_id=event.session_id,
            event_type=event.event_type,
            query=event.query,
            query_type=event.query_type,
            filters=filters,
            shown=shown,
            target_id=event.target_id,
            rank=event.rank,
            dwell_ms=event.dwell_ms,
            referrer=event.referrer,
            user_agent=request.headers.get("user-agent"),
            ip_hash=_hash_ip(_client_ip(request)),
        )
    except Exception:  # pragma: no cover - analytics must never break a request
        logger.exception("record_event failed (event_type=%s)", getattr(event, "event_type", "?"))
