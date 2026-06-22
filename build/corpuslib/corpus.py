"""Single data-access layer for the offline build pipeline.

Vendored from cert_layoff_playground/corpuslib/corpus.py and adapted for this
repo: the build's staging slice (build/corpus_slice, produced by make_slice.py)
is the default CORPUS_ROOT, with the $CORPUS_ROOT env override kept. Decisions
load from CORPUS_ROOT/corpus/decisions; gold holdings + taxonomy load from
CORPUS_ROOT/summaries (the make_slice symlink points those at the production
summaries dir).

PRIVACY: decision records contain respondent names (roster, dispositions,
full_text). Nothing derived from them may be served unless de-identified to
District (ALJ) cites via deident.deidentify().
"""

import json
import os
from pathlib import Path

# The build's staging slice, produced by make_slice.py. Overridable via
# $CORPUS_ROOT so a caller can point at any other root with the same layout.
_DEFAULT_ROOT = str(Path(__file__).resolve().parents[1] / "corpus_slice")


def corpus_paths():
    """Resolve corpus locations. Override order: $CORPUS_ROOT > build slice."""
    root = Path(os.environ.get("CORPUS_ROOT") or _DEFAULT_ROOT)
    return {
        "root": root,
        "decisions": root / "corpus" / "decisions",
        "gold_holdings": root / "summaries" / "holdings.jsonl",
        "taxonomy": root / "summaries" / "taxonomy.json",
        "case_index": root / "summaries" / "case_index.jsonl",
    }


def load_decisions(year=None):
    """Yield (oah_case_no_stem, record) for every decision JSON in the slice.

    The yielded id is the file stem (year-prefixed, no leading "N"); the
    record's identity.oah_case_no carries the "N" form. Tolerant of malformed
    JSON — a bad file is skipped, not fatal.

    PRIVACY: records contain respondent names. De-identify any served text.
    """
    d = corpus_paths()["decisions"]
    for f in sorted(d.glob("*.json")):
        if year and not f.stem.startswith(str(year)):
            continue
        try:
            rec = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        yield f.stem, rec


def load_gold_holdings(years=None):
    """Yield gold-holding dicts from the human summary volumes (1979-2015).

    Already de-identified by the volumes' own convention (District + ALJ).
    Rows with a null category_raw are volume headers/front-matter — callers
    skip those. Filter with years=an int or an iterable of ints (sort_year).
    """
    if isinstance(years, int):
        years = {years}
    elif years is not None:
        years = set(years)
    path = corpus_paths()["gold_holdings"]
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                h = json.loads(line)
            except json.JSONDecodeError:
                continue
            if years is None or h.get("sort_year") in years:
                yield h


def load_taxonomy():
    return json.loads(corpus_paths()["taxonomy"].read_text())
