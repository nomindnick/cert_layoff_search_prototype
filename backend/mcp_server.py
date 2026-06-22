"""MCP server over the cert-layoff corpus (remote, streamable-HTTP).

Exposes the same structured retrieval the web app uses as MCP tools, so an
attorney can connect her own Claude to the corpus. Mounted on the main FastAPI
service at ``/mcp`` (see backend/main.py) — it reuses the indexes already loaded
in RAM via ``backend.store.store``; no separate process or second copy.

Design choices that matter (per PLAN.md thesis — "the UI does the analytical
work; outcome data skews ~79% district"):
  * every search response carries the per-issue ``insight`` block INCLUDING the
    corpus ``baseline_district`` win-rate, so the model is nudged to read
    win-rate against the baseline rather than quoting a bare percentage;
  * results are de-identified ("District (ALJ)") — the served records are
    already scrubbed at index-build time;
  * tool calls are logged to the same ``events`` table as the web app, so this
    surface keeps the analytics / eval relevance pool complete rather than
    bypassing it.

Auth is intentionally NOT enforced here in this phase — the OAuth layer that
claude.ai connectors expect is added separately. Do not expose the ``/mcp`` URL
publicly until that lands.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import Context, FastMCP

from backend.search.aggregate import compute_insight
from backend.search.engine import COLLECTIONS
from backend.store import store

# Reuse the web search router's exact, tested filter + relevance logic so the
# MCP and HTTP surfaces never drift.
from backend.routers.search import (
    RELEVANCE_RATIO,
    _build_filters,
    _matches_categories,
    _within_years,
    _year_key,
)
from backend.routers.decisions import _resolve_record

logger = logging.getLogger(__name__)

# stateless_http=True: each request is self-contained (robust behind Railway's
# proxy, single replica). Default streamable_http_path="/mcp" — main.py lifts the
# resulting Route("/mcp") into the app so the canonical no-slash URL resolves.
mcp = FastMCP(
    "cert-layoff-corpus",
    instructions=(
        "Structured search over California OAH proposed decisions on certificated "
        "(teacher) layoffs. The unit is the HOLDING, grouped by decision. Results "
        "are non-precedential and de-identified to 'District (ALJ)'. IMPORTANT: "
        "outcome data skews ~79% district-win corpus-wide — always read a slice's "
        "win_rate against insight.win_rate.baseline_district, never as a bare "
        "percentage. Every result is traceable to a real decision via its "
        "holding_id / oah_case_no; cite those, and prefer quoting the returned "
        "summary over inferring new holdings."
    ),
    stateless_http=True,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _request_token(ctx: Context) -> str | None:
    """Best-effort caller identity from the HTTP request (header or bearer).

    Used only for analytics attribution in this phase; the OAuth layer will set
    a verified identity later.
    """
    try:
        req = ctx.request_context.request
        if req is None:
            return None
        tok = req.headers.get("x-access-token")
        if not tok:
            auth = req.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                tok = auth[7:].strip()
        return (tok or "").strip() or None
    except Exception:
        return None


def _log(ctx: Context, event_type: str, **fields) -> None:
    """Append an analytics event; never raise into the tool."""
    try:
        from backend import db

        db.insert_event(
            user_token=_request_token(ctx),
            event_type=event_type,
            referrer="mcp",
            **fields,
        )
    except Exception:
        logger.debug("mcp event log failed", exc_info=True)


def _run_search(collection, query, filters, cats, year_start, year_end, mode):
    """Mirror routers.search: full match set, relevance-gate queries, post-filter
    year-range + multi-category, browse sorts recent-first. Returns the hit list."""
    query = (query or "").strip()
    has_filters = bool(filters or cats or year_start is not None or year_end is not None)
    hits = []
    if query or has_filters:
        hits = store.engine.search(
            collection,
            query,
            filters=filters or None,
            k=None,
            min_ratio=RELEVANCE_RATIO if query else 0.0,
            mode=mode,
        )
    hits = [
        h
        for h in hits
        if _within_years(h.get("meta") or {}, year_start, year_end)
        and _matches_categories(h.get("meta") or {}, cats)
    ]
    if not query:
        hits.sort(
            key=lambda h: (
                -_year_key(h.get("meta") or {}),
                str((h.get("meta") or {}).get("case_no") or ""),
            )
        )
    return hits


def _holding_view(hit, rank):
    m = hit.get("meta") or {}
    return {
        "holding_id": hit.get("id"),
        "oah_case_no": m.get("case_no"),
        "district": m.get("district"),
        "alj": m.get("alj"),
        "year": m.get("year"),
        "category": m.get("category"),
        "subtype": m.get("subtype"),
        "statement": m.get("statement"),
        "prevailing_party": m.get("prevailing_party"),
        "summary": m.get("summary"),
        "rank": rank,
    }


def _search_payload(hits, limit):
    """Shape a search response: total + insight (with baseline) over the FULL
    match set, then the top ``limit`` results."""
    insight = compute_insight(hits, store.baseline())
    results = [_holding_view(h, i) for i, h in enumerate(hits[:limit], start=1)]
    return {"total": len(hits), "insight": insight, "results": results}


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def search_holdings(
    ctx: Context,
    query: str = "",
    category: str = "",
    year_start: int | None = None,
    year_end: int | None = None,
    district: str = "",
    alj: str = "",
    prevailing_party: str = "",
    limit: int = 10,
) -> dict:
    """Hybrid (semantic + keyword) search over extracted holdings from OAH
    teacher-layoff decisions. The primary tool.

    Returns {total, insight, results}. ``insight`` aggregates the FULL match set:
    win_rate (district vs respondent) WITH baseline_district — read win-rate
    against that baseline, not as a bare number — plus top_subtypes and top_aljs.
    Each result has a holding_id ("caseno:idx", usable with get_holding /
    get_decision), a District (ALJ) cite, year, issue category/subtype, the
    prevailing party, and the house-style summary.

    Leave query empty to browse by filter alone. Filters: category (canonical
    issue id — see list_facets), year_start/year_end, district/alj (substring),
    prevailing_party ("district"|"respondent"|"mixed").
    """
    cats = [category] if category else []
    filters = _build_filters(cats, year_start, year_end, district, alj, prevailing_party)
    hits = _run_search("holdings", query, filters, cats, year_start, year_end, "hybrid")
    _log(
        ctx,
        "search",
        query=query or None,
        filters={
            "collection": "holdings",
            "category": category or None,
            "year_start": year_start,
            "year_end": year_end,
            "district": district or None,
            "alj": alj or None,
            "prevailing_party": prevailing_party or None,
        },
        shown=[{"holding_id": h.get("id"), "rank": i} for i, h in enumerate(hits[:limit], 1)],
    )
    return _search_payload(hits, limit)


@mcp.tool()
def search_gold_holdings(
    ctx: Context,
    query: str = "",
    category: str = "",
    year_start: int | None = None,
    year_end: int | None = None,
    district: str = "",
    alj: str = "",
    limit: int = 10,
) -> dict:
    """Hybrid search over the expert-curated annual-summary holdings (the "gold"
    layer, reaching back to 1979 — editorial selections of noteworthy holdings,
    not exhaustive, already de-identified). Same {total, insight, results} shape
    as search_holdings. Use for historical depth or when you want the holdings a
    human editor flagged as significant."""
    cats = [category] if category else []
    filters = _build_filters(cats, year_start, year_end, district, alj, "")
    hits = _run_search("gold_holdings", query, filters, cats, year_start, year_end, "hybrid")
    _log(
        ctx,
        "search",
        query=query or None,
        filters={"collection": "gold_holdings", "category": category or None},
        shown=[{"holding_id": h.get("id"), "rank": i} for i, h in enumerate(hits[:limit], 1)],
    )
    return _search_payload(hits, limit)


@mcp.tool()
def search_decisions(
    ctx: Context,
    query: str,
    year_start: int | None = None,
    year_end: int | None = None,
    limit: int = 10,
) -> dict:
    """BM25 full-text search over complete decision texts. Use when holding-level
    search misses — procedural details, witness discussion, or phrasing that
    never made it into a holding. Returns {total, results} of decision-level hits
    (oah_case_no, cite, year) — follow up with get_decision for the full record."""
    hits = _run_search("decisions", query, {}, [], year_start, year_end, "bm25")
    _log(
        ctx,
        "search",
        query=query or None,
        filters={"collection": "decisions"},
        shown=[{"holding_id": h.get("id"), "rank": i} for i, h in enumerate(hits[:limit], 1)],
    )
    results = []
    for rank, h in enumerate(hits[:limit], start=1):
        m = h.get("meta") or {}
        results.append(
            {
                "oah_case_no": h.get("id"),
                "district": m.get("district"),
                "alj": m.get("alj"),
                "year": m.get("year"),
                "rank": rank,
            }
        )
    return {"total": len(hits), "results": results}


@mcp.tool()
def get_holding(ctx: Context, holding_id: str) -> dict:
    """Full detail for one holding (id "caseno:idx" from a search result): issue,
    ruling, arguments by party, facts, authorities cited and how used, and the
    reasoning chain. De-identified."""
    case, sep, idx = holding_id.rpartition(":")
    if not sep or not case or not idx.isdigit():
        return {"error": f"malformed holding_id {holding_id!r} (expected 'caseno:idx')"}
    record = _resolve_record(case)
    if record is None:
        return {"error": f"unknown case {case}"}
    holdings = record.get("holdings") or []
    i = int(idx)
    holding = next((h for h in holdings if h.get("idx") == i), None)
    if holding is None and 0 <= i < len(holdings):
        holding = holdings[i]
    if holding is None:
        return {"error": f"no holding {i} in {case}"}
    _log(ctx, "expand_holding", target_id=holding_id)
    return holding


@mcp.tool()
def get_decision(ctx: Context, oah_case_no: str, include_full_text: bool = False) -> dict:
    """One full decision record: identity (District/ALJ/date), board action,
    overall outcome, and all holdings. De-identified. full_text is excluded by
    default (large) — set include_full_text=True to include the clean reader text."""
    record = _resolve_record(oah_case_no)
    if record is None:
        return {"error": f"decision not found: {oah_case_no}"}
    _log(ctx, "open_decision", target_id=record.get("oah_case_no") or oah_case_no)
    if include_full_text:
        return record
    return {k: v for k, v in record.items() if k != "full_text"}


@mcp.tool()
def list_facets(collection: str = "holdings") -> dict:
    """Available filter values with counts: issue categories (canonical ids for
    the category filter), year range, top districts, top ALJs, and corpus stats
    (including the baseline district win-rate). Collections: holdings,
    gold_holdings, decisions."""
    if collection not in COLLECTIONS:
        return {"error": f"unknown collection {collection!r}; choose one of {list(COLLECTIONS)}"}
    meta = store.metadata or {}
    return {
        "categories": (meta.get("taxonomy") or {}).get("categories") or [],
        "districts": (meta.get("facets") or {}).get("districts") or [],
        "aljs": (meta.get("facets") or {}).get("aljs") or [],
        "corpus_stats": meta.get("corpus_stats") or {},
    }
