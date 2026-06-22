"""POST /api/events — analytics ingest, and GET /api/me — token confirmation.

Events are fire-and-forget: ``record_event`` never raises, so the endpoint
always returns ``{ok: true}``. ``/api/me`` lets the SPA confirm a valid token
and obtain the logged-in display name.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend import analytics
from backend.auth import get_user, require_user
from backend.models import EventIn

router = APIRouter(prefix="/api", tags=["events"])


@router.post("/events")
def post_event(event: EventIn, request: Request, _token: str = Depends(require_user)):
    analytics.record_event(request, event)
    return {"ok": True}


@router.get("/me")
def me(request: Request, _token: str = Depends(require_user)):
    return {"name": get_user(request)}
