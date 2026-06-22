#!/usr/bin/env python3
"""Build the two JSON artifacts the backend serves at runtime.

  build/output/records.json   dict: case_no -> a SERVED decision record
  build/output/metadata.json  corpus_stats + taxonomy + facets

Every served text field (full_text, holding statements/summaries/reasoning/
arguments/facts quotes) is passed through corpuslib.deident.deidentify() at
BUILD time, and roster names are DROPPED entirely — the served layer is
"District (ALJ)"-safe by construction. The original PDFs on R2 keep names
(acceptable per the relaxed-privacy stance).

case_no keys are the identity.oah_case_no form (with the leading "N").
pdf_url = $R2_DOC_BASE_URL (may be empty) + /docs/{year}/{stem}.pdf, where stem
is the year-prefixed filename stem (no "N"), matching convert_docs.py output.

Usage: python build/build_records.py
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # vendored corpuslib lives in build/

os.environ.setdefault("CORPUS_ROOT", str(HERE / "corpus_slice"))

from corpuslib import load_decisions, load_gold_holdings, load_taxonomy  # noqa: E402
from corpuslib.deident import alj_surname, deidentify, district_short  # noqa: E402
from build_index import derive_year  # noqa: E402  (robust year derivation)

OUT = HERE / "output"

R2_DOC_BASE_URL = os.environ.get("R2_DOC_BASE_URL", "")

# Taxonomy section labels (house-style), mirrored from render_summary.py so the
# served taxonomy facet carries human labels. Categories absent here fall back
# to a title-cased id.
CATEGORY_LABELS = {
    "procedural_issues": "Procedural Issues",
    "calculations_ada_fte": "ADA and FTE Calculations",
    "attrition": "Attrition",
    "pks_not_allowed": "PKS Not Allowed",
    "pks_allowed": "PKS Allowed",
    "pks_reduction": "Reduction of Particular Kinds of Services",
    "seniority": "Seniority",
    "temporary_employees": "Temporary Employees",
    "categorically_funded": "Categorically Funded Programs",
    "substitutes": "Substitute Employees",
    "skipping": "Skipping",
    "bumping": "Bumping",
    "assignments_reassignments": "Assignments and Reassignments",
    "credentials": "Credentials",
    "competency": "Competency",
    "tie_breaking": "Tie-Breaking Criteria",
    "domino_theory": "Domino Theory",
    "eera_cba_aa": "EERA and Collective Bargaining Issues",
    "contractual_issues": "Contractual Issues",
    "county_office_issues": "County Office of Education Issues",
    "discrimination": "Discrimination",
    "adult_education": "Adult Education",
    "reemployment_rights": "Reemployment Rights",
    "miscellaneous": "Miscellaneous",
    "other": "Other Issues",
}


def _label(key):
    return CATEGORY_LABELS.get(key) or (key or "").replace("_", " ").title()


def _deid_quote(q, rec):
    """De-identify a {quote: "..."} wrapper (arguments/facts), returning a str."""
    if isinstance(q, dict):
        text = q.get("quote") or ""
    else:
        text = q or ""
    if not text:
        return ""
    out, _ = deidentify(text, rec)
    return out


def served_holding(h, rec, idx):
    """Project + de-identify one holding into the served shape."""
    issue = h.get("issue") or {}
    ruling = h.get("ruling") or {}
    reasoning = h.get("reasoning") or {}

    stmt, _ = deidentify(issue.get("statement") or "", rec)
    ssh, _ = deidentify(h.get("summary_style_holding") or "", rec)
    reason_summary, _ = deidentify(reasoning.get("summary") or "", rec)
    reason_quotes = [
        _deid_quote(q, rec) for q in (reasoning.get("quotes") or [])
    ]
    reason_quotes = [q for q in reason_quotes if q]

    arguments = []
    for a in (h.get("arguments") or []):
        summ, _ = deidentify(a.get("summary") or "", rec)
        arguments.append({
            "party": a.get("party"),
            "summary": summ,
            "quote": _deid_quote(a.get("quote"), rec),
        })

    facts = []
    for fct in (h.get("facts") or []):
        summ, _ = deidentify(fct.get("summary") or "", rec)
        facts.append({
            "summary": summ,
            "quote": _deid_quote(fct.get("quote"), rec),
        })

    authorities = []
    for au in (h.get("authorities") or []):
        prop, _ = deidentify(au.get("proposition") or "", rec)
        authorities.append({
            "raw_cite": au.get("raw_cite"),
            "type": au.get("type"),
            "role": au.get("role"),
            "proposition": prop,
        })

    notable = h.get("notable") or {}
    note, _ = deidentify(notable.get("note") or "", rec) if notable.get("note") else ("", 0)

    return {
        "idx": idx,
        "issue": {
            "category": issue.get("category"),
            "subtype": issue.get("subtype"),
            "statement": stmt,
        },
        "prevailing_party": ruling.get("prevailing_party"),
        "remedies": ruling.get("remedies") or [],
        "affected_respondents": ruling.get("affected_respondents") or [],
        "arguments": arguments,
        "facts": facts,
        "authorities": authorities,
        "reasoning": {"summary": reason_summary, "quotes": reason_quotes},
        "summary_style_holding": ssh,
        "notable": {"flag": bool(notable.get("flag")), "note": note},
    }


def served_record(stem, rec):
    """Project + de-identify a full decision record into the served shape.
    Roster names are DROPPED; only the count is kept."""
    ident = rec.get("identity") or {}
    case_no = ident.get("oah_case_no") or stem
    district_raw = (ident.get("district") or {}).get("raw") or ""
    alj_raw = (ident.get("alj") or {}).get("raw") or ""
    year = derive_year(stem, rec)
    outcome = rec.get("outcome") or {}
    board = rec.get("board_action") or {}

    services = [
        {"description": (s or {}).get("description")}
        for s in (board.get("services_reduced") or [])
    ]

    full_text, _ = deidentify(rec.get("full_text") or "", rec)

    holdings = [
        served_holding(h, rec, i)
        for i, h in enumerate(rec.get("holdings") or [])
    ]

    pdf_url = None
    if R2_DOC_BASE_URL and year:
        pdf_url = f"{R2_DOC_BASE_URL.rstrip('/')}/docs/{year}/{stem}.pdf"

    return {
        "oah_case_no": case_no,
        "district": district_short(district_raw),
        "alj": alj_surname(alj_raw),
        "year": year,
        "decision_date": ident.get("decision_date"),
        "school_year_affected": ident.get("school_year_affected"),
        "scope": ident.get("scope"),
        "decision_kind": ident.get("decision_kind"),
        "overall": outcome.get("overall"),
        "board_action": {
            "fte_reduced": board.get("fte_reduced") or {},
            "statutory_basis": board.get("statutory_basis"),
            "services_reduced": services,
        },
        "n_respondents": len(outcome.get("roster") or []),
        "holdings": holdings,
        "full_text": full_text,
        "pdf_url": pdf_url,
    }


def build_records():
    records = {}
    for stem, rec in load_decisions():
        try:
            sr = served_record(stem, rec)
        except Exception as e:  # never let one bad record kill the build
            print(f"  skip {stem}: {e}", file=sys.stderr)
            continue
        records[sr["oah_case_no"]] = sr
    return records


def build_metadata(records):
    n_decisions = len(records)
    n_holdings = 0
    dist_win = 0
    party_total = 0  # holdings with a district/respondent/mixed ruling

    cat_counts = Counter()
    subtype_counts = Counter()
    year_counts = Counter()
    district_counts = Counter()
    alj_counts = Counter()
    years = set()

    for rec in records.values():
        y = rec.get("year")
        if y:
            year_counts[y] += 1
            years.add(y)
        if rec.get("district"):
            district_counts[rec["district"]] += 1
        if rec.get("alj"):
            alj_counts[rec["alj"]] += 1
        for h in rec.get("holdings") or []:
            n_holdings += 1
            cat = (h.get("issue") or {}).get("category")
            if cat:
                cat_counts[cat] += 1
            sub = (h.get("issue") or {}).get("subtype")
            if sub:
                subtype_counts[sub] += 1
            pp = h.get("prevailing_party")
            if pp in ("district", "respondent", "mixed"):
                party_total += 1
                if pp == "district":
                    dist_win += 1

    baseline = round(dist_win / party_total, 4) if party_total else 0.79

    # Gold holdings count (rows with a real category, per the index convention).
    n_gold = 0
    for h in load_gold_holdings():
        if h.get("category_raw") and (h.get("text") or "").strip():
            n_gold += 1

    year_ints = sorted(int(y) for y in years if str(y).isdigit())
    year_min = year_ints[0] if year_ints else None
    year_max = year_ints[-1] if year_ints else None

    # taxonomy: canonical_order from taxonomy.json, with served counts.
    try:
        tax = load_taxonomy()
        canonical = tax.get("canonical_order") or []
    except Exception:
        canonical = []
    seen = set()
    tax_categories = []
    for key in canonical:
        if key in seen:
            continue
        seen.add(key)
        tax_categories.append({
            "key": key, "label": _label(key), "count": cat_counts.get(key, 0),
        })
    # any categories present in the corpus but missing from the taxonomy order
    for key in sorted(cat_counts):
        if key not in seen:
            tax_categories.append({
                "key": key, "label": _label(key), "count": cat_counts[key],
            })

    facets = {
        "categories": dict(cat_counts.most_common()),
        "years": sorted(year_counts, key=lambda y: y),
        "districts": [
            {"name": n, "count": c} for n, c in district_counts.most_common()
        ],
        "aljs": [
            {"name": n, "count": c} for n, c in alj_counts.most_common()
        ],
    }

    return {
        "generated_at": None,
        "corpus_stats": {
            "n_decisions": n_decisions,
            "n_holdings": n_holdings,
            "n_gold": n_gold,
            "year_min": year_min,
            "year_max": year_max,
            "baseline_district_win_rate": baseline,
        },
        "taxonomy": {"categories": tax_categories},
        "facets": facets,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = build_records()
    metadata = build_metadata(records)

    records_path = OUT / "records.json"
    tmp = records_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False))
    tmp.replace(records_path)

    metadata_path = OUT / "metadata.json"
    tmp = metadata_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=1))
    tmp.replace(metadata_path)

    cs = metadata["corpus_stats"]
    print(f"records.json:  {len(records)} decisions -> {records_path}")
    print(f"metadata.json: {cs['n_holdings']} holdings, {cs['n_gold']} gold, "
          f"baseline district win {cs['baseline_district_win_rate']}, "
          f"years {cs['year_min']}-{cs['year_max']} -> {metadata_path}")
    if not R2_DOC_BASE_URL:
        print("note: R2_DOC_BASE_URL unset — pdf_url left null on every record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
