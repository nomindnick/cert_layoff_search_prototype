"""Deterministic report assembly (no LLM).

``build_report`` filters the Store's served, already de-identified decision
records by the report parameters (categories, year range, district/ALJ
substrings), groups the matching holdings by ``issue.category`` in the frozen
taxonomy's canonical order, and renders each holding's ``summary_style_holding``
as a numbered house-style entry ending in "— District (ALJ)" with an anchor to
the in-app decision reader. The output mirrors the traditional annual "Layoff
Decision Summaries" volume (see cert_layoff_corpus/pipeline/render_summary.py).

``to_pdf`` turns the rendered HTML into PDF bytes via xhtml2pdf (pisa). The
import is guarded so the app boots without the dependency; the router turns the
raised RuntimeError into a 501.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

# ---------------------------------------------------------------------------
# House-style constants (ported from render_summary.py)
# ---------------------------------------------------------------------------

# Section headings in the human volumes' register. Categories absent from the
# map fall back to the canonical id, with underscores → spaces, upper-cased.
DISPLAY = {
    "procedural_issues": "PROCEDURAL ISSUES",
    "calculations_ada_fte": "ADA AND FTE CALCULATIONS",
    "attrition": "ATTRITION",
    "pks_reduction": "REDUCTION OF PARTICULAR KINDS OF SERVICES",
    "pks_not_allowed": "REDUCTION OF PARTICULAR KINDS OF SERVICES",
    "pks_allowed": "REDUCTION OF PARTICULAR KINDS OF SERVICES",
    "seniority": "ISSUES RELATED TO SENIORITY",
    "temporary_employees": "TEMPORARY EMPLOYEES",
    "categorically_funded": "CATEGORICALLY FUNDED PROGRAMS",
    "substitutes": "SUBSTITUTE EMPLOYEES",
    "skipping": "SKIPPING",
    "bumping": "BUMPING",
    "assignments_reassignments": "ASSIGNMENTS AND REASSIGNMENTS",
    "credentials": "CREDENTIALS",
    "competency": "COMPETENCY",
    "tie_breaking": "TIE-BREAKING CRITERIA",
    "domino_theory": "DOMINO THEORY",
    "eera_cba_aa": "EERA AND COLLECTIVE BARGAINING ISSUES",
    "contractual_issues": "CONTRACTUAL ISSUES",
    "county_office_issues": "COUNTY OFFICE OF EDUCATION ISSUES",
    "discrimination": "DISCRIMINATION",
    "adult_education": "ADULT EDUCATION",
    "reemployment_rights": "REEMPLOYMENT RIGHTS",
    "miscellaneous": "MISCELLANEOUS",
    "other": "OTHER ISSUES",
}

# Fallback canonical order if the Store metadata carries no taxonomy. Mirrors
# taxonomy.json's canonical_order (with the two legacy pks_* ids collapsed onto
# a single reduction-of-services slot).
FALLBACK_ORDER = [
    "procedural_issues",
    "calculations_ada_fte",
    "attrition",
    "pks_reduction",
    "seniority",
    "temporary_employees",
    "categorically_funded",
    "substitutes",
    "skipping",
    "bumping",
    "assignments_reassignments",
    "credentials",
    "competency",
    "tie_breaking",
    "domino_theory",
    "eera_cba_aa",
    "contractual_issues",
    "county_office_issues",
    "discrimination",
    "adult_education",
    "reemployment_rights",
    "miscellaneous",
    "other",
]

# The schema's outcome-neutral reduction-of-services category sits where the
# volumes' outcome pair sat; both legacy ids collapse onto it for ordering.
LEGACY_CATEGORY = {
    "pks_allowed": "pks_reduction",
    "pks_not_allowed": "pks_reduction",
}

# Matches a trailing "(Name)" or "(Name)." citation tail, so we don't append a
# second District (ALJ) cite when the model's paragraph already carries one.
_CITE_TAIL = re.compile(r"\([A-Z][a-zA-Z.À-ſ'\- ]+\)\.?\s*$")

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def roman(n: int) -> str:
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
            (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
            (5, "V"), (4, "IV"), (1, "I")]
    out = []
    for v, s in vals:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def _section_title(cat: str) -> str:
    return DISPLAY.get(cat, (cat or "other").replace("_", " ").upper())


def _norm_case(case_no: Optional[str]) -> str:
    """Bare OAH case number with any single leading N dropped, for cites."""
    c = (case_no or "").strip()
    if c[:1] in ("N", "n") and len(c) > 1 and c[1].isdigit():
        return c[1:]
    return c


def _coerce_year(value: Any) -> Optional[int]:
    """Best-effort int year from a record's ``year`` (int, str, or None)."""
    if value is None:
        return None
    try:
        return int(str(value)[:4])
    except (ValueError, TypeError):
        return None


def _category_order(store: Any) -> list[str]:
    """Canonical category order from Store metadata if present, else fallback.

    Reads metadata.taxonomy.categories[*].key (the served taxonomy shape per
    the build contract); legacy pks_* keys collapse onto pks_reduction.
    """
    order: list[str] = []
    seen: set[str] = set()
    meta = getattr(store, "metadata", None) or {}
    tax = (meta.get("taxonomy") or {}) if isinstance(meta, dict) else {}
    cats = tax.get("categories") or []
    for c in cats:
        key = (c or {}).get("key") if isinstance(c, dict) else None
        key = LEGACY_CATEGORY.get(key, key)
        if key and key not in seen:
            order.append(key)
            seen.add(key)
    if not order:
        order = list(FALLBACK_ORDER)
        seen = set(order)
    # Always have a trailing catch-all for unforeseen categories.
    if "other" not in seen:
        order.append("other")
    return order


# ---------------------------------------------------------------------------
# Entry text (verbatim summary_style_holding + cite tail)
# ---------------------------------------------------------------------------

def _entry_text(holding: dict, cite: str, case_no: Optional[str]) -> str:
    """The per-entry paragraph: ``summary_style_holding`` verbatim, with the
    "District (ALJ)" citation appended when the paragraph lacks one, and the OAH
    case number appended to the citation. Text is already de-identified at build
    time, so this never touches names. Mirrors render_summary.entry_text."""
    text = (holding.get("summary_style_holding") or "").strip()
    if not text:
        issue = ((holding.get("issue") or {}).get("statement") or "").strip()
        party = holding.get("prevailing_party")
        tail = {
            "district": "The ALJ resolved the issue in the District's favor.",
            "respondent": "The ALJ resolved the issue in the respondent's favor.",
            "mixed": "The ALJ resolved the issue with mixed results.",
        }.get(party, "")
        text = f"{issue} {tail}".strip()
    if not text:
        return ""
    if not _CITE_TAIL.search(text):
        text = f"{text.rstrip('.')}. {cite}"
    bare = _norm_case(case_no)
    if bare and f"OAH No. {bare}" not in text and f"OAH No. N{bare}" not in text:
        text = f"{text.rstrip('.')}, OAH No. {bare}"
    if not text.endswith("."):
        text += "."
    return text


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def build_report(store: Any, params: dict) -> dict:
    """Assemble the deterministic house-style report.

    Parameters (all optional except an implicit "everything"):
        categories : list[str]   issue categories to include (empty/None = all)
        year_start : int | None
        year_end   : int | None
        district   : str | None  substring match on the served short district
        alj        : str | None  substring match on the served ALJ surname

    Returns: {"html": str, "n_holdings": int, "title": str, "groups": list}
    where each group is {"category", "title", "roman", "entries": [...]}.
    """
    params = params or {}
    raw_cats = params.get("categories") or []
    if isinstance(raw_cats, str):
        raw_cats = [c.strip() for c in raw_cats.split(",") if c.strip()]
    # Normalize requested categories through the legacy collapse so a request
    # for "pks_allowed" still gathers the unified reduction-of-services bucket.
    want_cats = {LEGACY_CATEGORY.get(c, c) for c in raw_cats if c}

    year_start = _coerce_year(params.get("year_start"))
    year_end = _coerce_year(params.get("year_end"))
    district = (params.get("district") or "").strip()
    alj = (params.get("alj") or "").strip()

    records = getattr(store, "records", {}) or {}

    by_cat: dict[str, list[dict]] = {}
    n_holdings = 0
    matched_cases: set[str] = set()
    years_seen: list[int] = []

    for case_no, rec in records.items():
        if not isinstance(rec, dict):
            continue
        # Decision-level district / ALJ substring filters.
        if district:
            d = (rec.get("district") or rec.get("district_raw") or "").lower()
            if district.lower() not in d:
                continue
        if alj:
            a = (rec.get("alj") or rec.get("alj_raw") or "").lower()
            if alj.lower() not in a:
                continue

        ryear = _coerce_year(rec.get("year"))
        if year_start is not None and (ryear is None or ryear < year_start):
            continue
        if year_end is not None and (ryear is None or ryear > year_end):
            continue

        dist = rec.get("district") or rec.get("district_raw") or ""
        surname = rec.get("alj") or rec.get("alj_raw") or ""
        cite = f"{dist} ({surname})".strip() if dist or surname else ""
        case_id = rec.get("oah_case_no") or case_no

        for h in rec.get("holdings") or []:
            if not isinstance(h, dict):
                continue
            cat = ((h.get("issue") or {}).get("category")) or "other"
            cat = LEGACY_CATEGORY.get(cat, cat)
            if want_cats and cat not in want_cats:
                continue
            text = _entry_text(h, cite, case_id)
            if not text:
                continue
            n_holdings += 1
            matched_cases.add(case_id)
            if ryear is not None:
                years_seen.append(ryear)
            by_cat.setdefault(cat, []).append({
                "case_no": case_id,
                "district": dist,
                "alj": surname,
                "prevailing_party": h.get("prevailing_party"),
                "subtype": (h.get("issue") or {}).get("subtype"),
                "notable": bool((h.get("notable") or {}).get("flag"))
                if isinstance(h.get("notable"), dict) else bool(h.get("notable")),
                "text": text,
            })

    # Order categories by the frozen taxonomy; append any stragglers sorted.
    canonical = _category_order(store)
    order = [c for c in canonical if c in by_cat]
    order += sorted(c for c in by_cat if c not in order)

    groups = []
    for i, cat in enumerate(order, 1):
        entries = sorted(
            by_cat[cat],
            key=lambda e: ((e["district"] or "").lower(), e["case_no"]),
        )
        groups.append({
            "category": cat,
            "title": _section_title(cat),
            "roman": roman(i),
            "entries": entries,
        })

    # ---- Title + header context ------------------------------------------
    if want_cats:
        labels = [_section_title(c).title() for c in canonical if c in want_cats]
        # Pick up any requested categories not in the canonical list too.
        labels += [_section_title(c).title()
                   for c in sorted(want_cats) if c not in canonical]
        cat_label = ", ".join(dict.fromkeys(labels)) or "Selected Issues"
    else:
        cat_label = "All Issues"

    if years_seen:
        ymin, ymax = min(years_seen), max(years_seen)
    else:
        ymin = year_start
        ymax = year_end
    if ymin is not None and ymax is not None:
        year_label = f"{ymin}" if ymin == ymax else f"{ymin}–{ymax}"
    elif ymin is not None:
        year_label = f"{ymin}–"
    elif ymax is not None:
        year_label = f"–{ymax}"
    else:
        year_label = "All Years"

    title = f"Certificated Layoff Decisions — {cat_label}, {year_label}"

    corpus_stats = {}
    meta = getattr(store, "metadata", None) or {}
    if isinstance(meta, dict):
        corpus_stats = meta.get("corpus_stats") or {}

    context = {
        "title": title,
        "category_label": cat_label,
        "year_label": year_label,
        "groups": groups,
        "n_holdings": n_holdings,
        "n_decisions": len(matched_cases),
        "n_sections": len(groups),
        "generated_at": datetime.date.today().isoformat(),
        "corpus_stats": corpus_stats,
        "filters": {
            "district": district,
            "alj": alj,
            "year_start": year_start,
            "year_end": year_end,
        },
    }

    html = _render_html(context)
    return {
        "html": html,
        "n_holdings": n_holdings,
        "title": title,
        "groups": groups,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_env: Optional[Environment] = None


def _get_env() -> Environment:
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _env


def _render_html(context: dict) -> str:
    return _get_env().get_template("report.html").render(**context)


# ---------------------------------------------------------------------------
# PDF (xhtml2pdf / pisa) — import-guarded
# ---------------------------------------------------------------------------

def to_pdf(html: str) -> bytes:
    """Render the report HTML to PDF bytes via xhtml2pdf (pisa).

    The import is guarded so the application boots without xhtml2pdf installed;
    the report router converts the RuntimeError into an HTTP 501.
    """
    try:
        from xhtml2pdf import pisa  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised only without dep
        raise RuntimeError(
            "PDF generation is unavailable: the 'xhtml2pdf' package is not "
            "installed in this environment."
        ) from exc

    import io

    buf = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=buf, encoding="utf-8")
    if getattr(result, "err", 0):
        raise RuntimeError("PDF generation failed while rendering the report.")
    return buf.getvalue()
