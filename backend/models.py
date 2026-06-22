"""Pydantic response/request models for the HTTP API.

Models are deliberately permissive (Optional fields, defaults) so a record with
schema gaps (the corpus mixes v0.2.0 and v0.4.0) never breaks serialization.
These mirror the response shapes in the build contract / PLAN.md §5.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
class IssueRef(BaseModel):
    category: Optional[str] = None
    subtype: Optional[str] = None
    statement: Optional[str] = None


class HoldingHit(BaseModel):
    holding_id: str
    oah_case_no: Optional[str] = None
    district: Optional[str] = None
    alj: Optional[str] = None
    year: Optional[Any] = None
    issue: IssueRef = Field(default_factory=IssueRef)
    prevailing_party: Optional[str] = None
    remedies: list[str] = Field(default_factory=list)
    summary_style_holding: Optional[str] = None
    rank: int = 0


class WinRate(BaseModel):
    district: float = 0.0
    respondent: float = 0.0
    mixed: float = 0.0
    baseline_district: float = 0.0


class NamedCount(BaseModel):
    name: Optional[str] = None
    count: int = 0


class TrendPoint(BaseModel):
    year: int
    district: int = 0
    respondent: int = 0
    mixed: int = 0
    total: int = 0


class Insight(BaseModel):
    decision_count: int = 0
    holding_count: int = 0
    year_range: Optional[list[int]] = None
    win_rate: WinRate = Field(default_factory=WinRate)
    top_categories: list[NamedCount] = Field(default_factory=list)
    top_subtypes: list[NamedCount] = Field(default_factory=list)
    top_aljs: list[NamedCount] = Field(default_factory=list)
    trend: list[TrendPoint] = Field(default_factory=list)


class SearchResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 20
    insight: Insight = Field(default_factory=Insight)
    results: list[HoldingHit] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Decision detail (the served record, permissive passthrough)
# --------------------------------------------------------------------------- #
class HoldingDetail(BaseModel):
    idx: Optional[int] = None
    issue: IssueRef = Field(default_factory=IssueRef)
    prevailing_party: Optional[str] = None
    remedies: list[str] = Field(default_factory=list)
    affected_respondents: list[Any] = Field(default_factory=list)
    arguments: list[dict[str, Any]] = Field(default_factory=list)
    facts: list[dict[str, Any]] = Field(default_factory=list)
    authorities: list[dict[str, Any]] = Field(default_factory=list)
    reasoning: dict[str, Any] = Field(default_factory=dict)
    summary_style_holding: Optional[str] = None
    notable: dict[str, Any] = Field(default_factory=dict)


class BoardAction(BaseModel):
    fte_reduced: dict[str, Any] = Field(default_factory=dict)
    statutory_basis: Optional[Any] = None
    services_reduced: list[dict[str, Any]] = Field(default_factory=list)


class DecisionDetail(BaseModel):
    oah_case_no: Optional[str] = None
    district: Optional[str] = None
    alj: Optional[str] = None
    year: Optional[Any] = None
    decision_date: Optional[str] = None
    school_year_affected: Optional[str] = None
    scope: Optional[Any] = None
    decision_kind: Optional[str] = None
    overall: Optional[str] = None
    board_action: BoardAction = Field(default_factory=BoardAction)
    n_respondents: int = 0
    holdings: list[HoldingDetail] = Field(default_factory=list)
    full_text: Optional[str] = None
    pdf_url: Optional[str] = None

    model_config = {"extra": "allow"}


# --------------------------------------------------------------------------- #
# Facets
# --------------------------------------------------------------------------- #
class CategoryFacet(BaseModel):
    key: Optional[str] = None
    label: Optional[str] = None
    count: int = 0


class FacetsResponse(BaseModel):
    categories: list[CategoryFacet] = Field(default_factory=list)
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    districts: list[NamedCount] = Field(default_factory=list)
    aljs: list[NamedCount] = Field(default_factory=list)
    corpus_stats: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
class ReportRequest(BaseModel):
    categories: list[str] = Field(default_factory=list)
    year_start: Optional[int] = None
    year_end: Optional[int] = None
    district: Optional[str] = None
    alj: Optional[str] = None
    format: str = "html"  # "html" | "pdf"


# --------------------------------------------------------------------------- #
# Events (analytics)
# --------------------------------------------------------------------------- #
class EventIn(BaseModel):
    event_type: str
    session_id: Optional[str] = None
    query: Optional[str] = None
    query_type: Optional[str] = None
    filters: Optional[dict[str, Any]] = None
    shown: Optional[Any] = None
    target_id: Optional[str] = None
    rank: Optional[int] = None
    dwell_ms: Optional[int] = None
    referrer: Optional[str] = None
