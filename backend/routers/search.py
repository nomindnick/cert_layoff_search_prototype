"""GET /api/search — hybrid holding search with insight + pagination.

Over-fetches up to 200 hits from the engine, computes the insight strip over the
full match set, then paginates 20 per page. Raw relevance scores are never
exposed to the client (rank only). The server does NOT log search events — the
client logs the shown holding ids (which carry the leakage-free relevance pool).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from backend.auth import require_user
from backend.models import HoldingHit, Insight, SearchResponse
from backend.search.aggregate import compute_insight
from backend.store import store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["search"])

PAGE_SIZE = 20
# Query-mode relevance gate: keep holdings whose BM25 score is >= this fraction
# of the top score, trimming the weak single-common-term tail so totals and the
# insight strip reflect genuinely relevant matches. Tunable. Browse uses 0.0.
RELEVANCE_RATIO = 0.25


def _year_key(meta: dict) -> int:
    try:
        return int(str(meta.get("year"))[:4])
    except (TypeError, ValueError):
        return 0


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _build_filters(
    categories: list[str],
    year_start: int | None,
    year_end: int | None,
    district: str | None,
    alj: str | None,
    prevailing_party: str | None,
) -> dict:
    """Filters consumed by Engine._match. Categories map to the engine's
    ``category`` key (membership-tested against meta.categories or .category).
    Year is a single-value match in the engine, so a range is applied here by
    leaving year out of the engine filter and trimming the hit list afterward.
    """
    filters: dict = {}
    # The engine matches one category at a time; pass the first and apply any
    # remaining categories as an OR post-filter below. Most UI use is a single
    # category, and over-fetch keeps recall high.
    if categories:
        filters["category"] = categories[0]
    if district:
        filters["district"] = district
    if alj:
        filters["alj"] = alj
    if prevailing_party:
        filters["prevailing_party"] = prevailing_party
    return filters


def _within_years(meta: dict, year_start: int | None, year_end: int | None) -> bool:
    if year_start is None and year_end is None:
        return True
    y = meta.get("year")
    try:
        y = int(y)
    except (TypeError, ValueError):
        return False
    if year_start is not None and y < year_start:
        return False
    if year_end is not None and y > year_end:
        return False
    return True


def _matches_categories(meta: dict, categories: list[str]) -> bool:
    if len(categories) <= 1:
        return True  # single/zero category already handled by the engine filter
    wanted = set(categories)
    cats = meta.get("categories")
    if cats:
        return bool(wanted & set(cats))
    return meta.get("category") in wanted


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query("", description="Search query"),
    categories: str | None = Query(None, description="Comma-separated category keys"),
    year_start: int | None = Query(None),
    year_end: int | None = Query(None),
    district: str | None = Query(None),
    alj: str | None = Query(None),
    prevailing_party: str | None = Query(None, description="district|respondent|mixed"),
    collection: str = Query("holdings"),
    page: int = Query(1, ge=1),
    _token: str = Depends(require_user),
):
    cats = _csv(categories)
    filters = _build_filters(cats, year_start, year_end, district, alj, prevailing_party)

    query = (q or "").strip()
    # Browse-by-filter: run the engine whenever there is a query OR any active
    # filter (category/year/district/alj/prevailing_party). An empty query with
    # filters yields all-zero BM25 scores, so the pre-filtered candidate set is
    # still ranked and returned — this powers the empty-state category pills and
    # FilterBar-only browsing. Only a truly empty request (no query, no filters)
    # short-circuits to [] rather than dumping the whole corpus.
    has_filters = bool(
        filters or cats or year_start is not None or year_end is not None
    )
    hits: list[dict] = []
    if query or has_filters:
        try:
            # k=None: return the full match set so total + insight are exact
            # (the corpus is tiny). Relevance-gate only when there's a query.
            hits = store.engine.search(
                collection, query, filters=filters or None, k=None,
                min_ratio=RELEVANCE_RATIO if query else 0.0,
            )
        except Exception:
            logger.exception("search engine error (collection=%s, q=%r)", collection, query)
            hits = []

    # Post-filter year range and multi-category OR (engine handles single-value).
    hits = [
        h
        for h in hits
        if _within_years(h.get("meta") or {}, year_start, year_end)
        and _matches_categories(h.get("meta") or {}, cats)
    ]

    # Browse (no query) has no relevance order — surface most recent first.
    if not query:
        hits.sort(key=lambda h: (-_year_key(h.get("meta") or {}),
                                 str((h.get("meta") or {}).get("case_no") or "")))

    # Insight is computed over the FULL relevant match set (not just the page).
    insight = Insight(**compute_insight(hits, store.baseline()))

    total = len(hits)
    start = (page - 1) * PAGE_SIZE
    page_hits = hits[start : start + PAGE_SIZE]

    results: list[HoldingHit] = []
    for rank, hit in enumerate(page_hits, start=start + 1):
        meta = hit.get("meta") or {}
        results.append(
            HoldingHit(
                holding_id=hit.get("id"),
                oah_case_no=meta.get("case_no"),
                district=meta.get("district"),
                alj=meta.get("alj"),
                year=meta.get("year"),
                issue={
                    "category": meta.get("category"),
                    "subtype": meta.get("subtype"),
                    "statement": meta.get("statement"),
                },
                prevailing_party=meta.get("prevailing_party"),
                remedies=meta.get("remedies") or [],
                summary_style_holding=meta.get("summary"),
                rank=rank,
            )
        )

    return SearchResponse(
        total=total,
        page=page,
        page_size=PAGE_SIZE,
        insight=insight,
        results=results,
    )
