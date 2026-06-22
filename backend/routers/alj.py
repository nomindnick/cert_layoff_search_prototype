"""GET /api/alj/{name} — per-ALJ scouting profile ("who's my judge").

Aggregates the served records for one ALJ surname into caseload, win-rate vs the
corpus baseline, a per-issue breakdown, a year trend, top sub-issues, and a few
representative holdings. This is the differentiator no public tool offers; the
computation lives in backend.search.aggregate.compute_alj_profile.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import require_user
from backend.search.aggregate import compute_alj_profile
from backend.store import store

router = APIRouter(prefix="/api", tags=["alj"])


@router.get("/alj/{name}")
def get_alj(name: str, _token: str = Depends(require_user)):
    profile = compute_alj_profile(store.records, name, store.baseline())
    if profile is None:
        raise HTTPException(status_code=404, detail="ALJ not found")
    return profile
