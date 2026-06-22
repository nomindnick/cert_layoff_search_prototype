"""GET /api/facets — filter values + counts that drive the filter UI.

Sourced entirely from the in-RAM metadata.json (no engine scan): taxonomy
categories, year range, top districts, top ALJs, and corpus stats.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.auth import require_user
from backend.models import FacetsResponse
from backend.store import store

router = APIRouter(prefix="/api", tags=["facets"])


@router.get("/facets", response_model=FacetsResponse)
def get_facets(_token: str = Depends(require_user)):
    meta = store.metadata or {}
    taxonomy = meta.get("taxonomy") or {}
    facets = meta.get("facets") or {}
    corpus_stats = meta.get("corpus_stats") or {}

    return FacetsResponse(
        categories=taxonomy.get("categories") or [],
        year_min=corpus_stats.get("year_min"),
        year_max=corpus_stats.get("year_max"),
        districts=facets.get("districts") or [],
        aljs=facets.get("aljs") or [],
        corpus_stats=corpus_stats,
    )
