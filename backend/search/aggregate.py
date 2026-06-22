"""Insight aggregation over a holding match-set.

``compute_insight`` turns a list of engine.search hits into the structured
signal the UI leads with: win-rate vs the corpus baseline, top sub-issues,
most-active ALJs, and a per-year trend split by prevailing party. All counts
are computed from ``hit["meta"]`` (the de-identified holding meta), never from
relevance scores. The win-rate baseline is always shown because the corpus is
heavily skewed toward district wins (~79%) — the deviation is the signal.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict


def _norm_subtype(s):
    """Canonical key for a holding subtype so near-identical phrasings collapse
    in the top-sub-issues list. Drops parenthetical statute refs, normalizes
    punctuation/whitespace, and sorts the slash-separated parts so reorderings
    ("A / B" vs "B / A") merge. Returns None for empty input."""
    if not s:
        return None
    t = str(s).lower()
    t = re.sub(r"\([^)]*\)", " ", t)          # drop "(§ 44955(d)(1))" etc.
    t = re.sub(r"[^a-z0-9/ ]+", " ", t)
    parts = sorted({" ".join(p.split()) for p in t.split("/") if p.strip()})
    return " / ".join(parts) if parts else None


def _year_int(v):
    """Coerce a year value (str/int/None) to int, or None if not a clean year."""
    if v is None:
        return None
    try:
        return int(str(v)[:4])
    except (ValueError, TypeError):
        return None


def compute_insight(results, baseline):
    """Aggregate engine.search hits into the insight payload.

    Args:
        results: list of hit dicts (each with a "meta" holding-meta dict).
        baseline: corpus-wide district win-rate (float) shown for comparison.

    Returns a dict with: decision_count, holding_count, year_range,
    win_rate{district,respondent,mixed,baseline_district}, top_categories,
    top_subtypes, top_aljs, trend (sorted by year).
    """
    metas = [(h.get("meta") or {}) for h in (results or [])]
    holding_count = len(metas)

    decisions = set()
    years = []
    cat_counts = Counter()
    subtype_counts = Counter()        # keyed by NORMALIZED subtype
    subtype_display = defaultdict(Counter)  # norm key -> {original: count}
    alj_counts = Counter()
    party_counts = Counter()
    # year -> {district, respondent, mixed, total}
    trend_map = defaultdict(lambda: {"district": 0, "respondent": 0, "mixed": 0, "total": 0})

    for m in metas:
        case_no = m.get("case_no")
        if case_no:
            decisions.add(case_no)

        y = _year_int(m.get("year"))
        if y is not None:
            years.append(y)

        cat = m.get("category")
        if cat:
            cat_counts[cat] += 1
        sub = m.get("subtype")
        if sub:
            key = _norm_subtype(sub)
            if key:
                subtype_counts[key] += 1
                subtype_display[key][sub] += 1
        alj = m.get("alj")
        if alj:
            alj_counts[alj] += 1

        party = m.get("prevailing_party")
        if party in ("district", "respondent", "mixed"):
            party_counts[party] += 1
        # else: none_ruled / unknown — excluded from win-rate denominator.

        if y is not None:
            bucket = trend_map[y]
            bucket["total"] += 1
            if party in ("district", "respondent", "mixed"):
                bucket[party] += 1

    # Win-rate over rulings that actually went one way (excludes none_ruled).
    ruled_total = party_counts["district"] + party_counts["respondent"] + party_counts["mixed"]
    if ruled_total:
        win_rate = {
            "district": round(party_counts["district"] / ruled_total, 4),
            "respondent": round(party_counts["respondent"] / ruled_total, 4),
            "mixed": round(party_counts["mixed"] / ruled_total, 4),
        }
    else:
        win_rate = {"district": 0.0, "respondent": 0.0, "mixed": 0.0}
    win_rate["baseline_district"] = round(float(baseline or 0.0), 4)

    year_range = [min(years), max(years)] if years else None

    trend = [
        {
            "year": y,
            "district": trend_map[y]["district"],
            "respondent": trend_map[y]["respondent"],
            "mixed": trend_map[y]["mixed"],
            "total": trend_map[y]["total"],
        }
        for y in sorted(trend_map)
    ]

    def _top(counter, key_name, n=8):
        return [{key_name: k, "count": c} for k, c in counter.most_common(n)]

    def _top_subtypes(n=8):
        # Display the most frequent original phrasing for each normalized group.
        out = []
        for key, c in subtype_counts.most_common(n):
            display = subtype_display[key].most_common(1)[0][0] if subtype_display[key] else key
            out.append({"name": display, "count": c})
        return out

    return {
        "decision_count": len(decisions),
        "holding_count": holding_count,
        "year_range": year_range,
        "win_rate": win_rate,
        "top_categories": _top(cat_counts, "name"),
        "top_subtypes": _top_subtypes(),
        "top_aljs": _top(alj_counts, "name"),
        "trend": trend,
    }


def compute_alj_profile(records, name, baseline):
    """Build an ALJ scouting profile from the served records.

    Matches decisions by ALJ surname (case-insensitive) and aggregates: caseload,
    win-rate vs the corpus baseline, per-issue breakdown with district win-rate,
    a year trend, top sub-issues, and a few representative holdings (respondent
    wins / flagged-notable surfaced first, since those are the rarer signal).
    Returns None when the ALJ has no decisions.
    """
    target = (name or "").strip().lower()
    if not target:
        return None

    holdings = []  # (record, holding)
    decisions = []
    for rec in records.values():
        if (rec.get("alj") or "").strip().lower() != target:
            continue
        decisions.append(rec)
        for h in (rec.get("holdings") or []):
            holdings.append((rec, h))
    if not decisions:
        return None

    # Reuse compute_insight for win_rate / trend / top_subtypes / year_range.
    pseudo = [
        {"meta": {
            "case_no": r.get("oah_case_no"),
            "year": r.get("year"),
            "category": (h.get("issue") or {}).get("category"),
            "subtype": (h.get("issue") or {}).get("subtype"),
            "alj": r.get("alj"),
            "prevailing_party": h.get("prevailing_party"),
        }}
        for r, h in holdings
    ]
    insight = compute_insight(pseudo, baseline)

    # Per-issue breakdown with district/respondent win-rate.
    cat = defaultdict(lambda: {"n": 0, "district": 0, "respondent": 0, "mixed": 0})
    districts = set()
    for r, h in holdings:
        c = (h.get("issue") or {}).get("category")
        p = h.get("prevailing_party")
        if c:
            cat[c]["n"] += 1
            if p in ("district", "respondent", "mixed"):
                cat[c][p] += 1
        d = r.get("district")
        if d:
            districts.add(d)
    issues = []
    for c, v in sorted(cat.items(), key=lambda kv: -kv[1]["n"]):
        ruled = v["district"] + v["respondent"] + v["mixed"]
        issues.append({
            "category": c,
            "n": v["n"],
            "district_win_rate": round(v["district"] / ruled, 4) if ruled else None,
            "respondent_win_rate": round(v["respondent"] / ruled, 4) if ruled else None,
        })

    def _rep_sort(rh):
        r, h = rh
        notable = 1 if (h.get("notable") or {}).get("flag") else 0
        resp = 1 if h.get("prevailing_party") == "respondent" else 0
        return (notable + resp, _year_int(r.get("year")) or 0)

    samples = []
    for r, h in sorted(holdings, key=_rep_sort, reverse=True)[:6]:
        issue = h.get("issue") or {}
        samples.append({
            "oah_case_no": r.get("oah_case_no"),
            "year": r.get("year"),
            "district": r.get("district"),
            "category": issue.get("category"),
            "subtype": issue.get("subtype"),
            "prevailing_party": h.get("prevailing_party"),
            "summary": h.get("summary_style_holding") or issue.get("statement"),
        })

    return {
        "name": decisions[0].get("alj") or name,
        "n_decisions": len(decisions),
        "n_holdings": len(holdings),
        "n_districts": len(districts),
        "year_range": insight["year_range"],
        "win_rate": insight["win_rate"],
        "top_subtypes": insight["top_subtypes"],
        "trend": insight["trend"],
        "issues": issues,
        "samples": samples,
    }
