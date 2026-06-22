#!/usr/bin/env python3
"""Stage the corpus slice the rest of the build reads from.

Builds a fresh staging root at build/corpus_slice/:
  corpus/decisions/   symlinks to every production decision (412, schema 0.4.0)
                      + the lab's 2004*/2009* decisions (267, schema 0.2.0)
  summaries/          a symlink to the production summaries dir (gold holdings,
                      taxonomy, case_index)

This is the corrected replacement for the stale cert_layoff_merged build (which
pointed at an old 174-record corpus). We union the two live sources directly:
  - cert_layoff_corpus/output/corpus/decisions/*.json      (production spine)
  - cert_layoff_lab/output/corpus/decisions/{2004,2009}*.json  (mid-decade fill)

Symlinks (not copies) keep the slice cheap and always current with the sources.
On a name collision (same stem in both sources) the production record wins.

Usage: python build/make_slice.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent

# Live source roots (read directly — do NOT use cert_layoff_merged).
CORPUS_DECISIONS = Path(
    "/home/nick/Projects/cert_layoff_corpus/output/corpus/decisions"
)
LAB_DECISIONS = Path(
    "/home/nick/Projects/cert_layoff_lab/output/corpus/decisions"
)
PROD_SUMMARIES = Path(
    "/home/nick/Projects/cert_layoff_corpus/output/summaries"
)

LAB_YEAR_PREFIXES = ("2004", "2009")

SLICE_ROOT = HERE / "corpus_slice"


def _link(src: Path, dst: Path):
    """Create/refresh a symlink dst -> src. Returns True if it now points at src."""
    if dst.is_symlink() or dst.exists():
        try:
            dst.unlink()
        except OSError:
            return False
    dst.symlink_to(src)
    return True


def main():
    decisions_dir = SLICE_ROOT / "corpus" / "decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)

    # Clear any stale decision symlinks from a prior run so removed source
    # files don't linger in the slice.
    for old in decisions_dir.iterdir():
        if old.is_symlink() or old.is_file():
            old.unlink()

    seen = set()
    n_corpus = 0
    n_lab = 0

    # Production spine first — it wins on any stem collision.
    if not CORPUS_DECISIONS.is_dir():
        raise SystemExit(f"production decisions dir missing: {CORPUS_DECISIONS}")
    for f in sorted(CORPUS_DECISIONS.glob("*.json")):
        if _link(f, decisions_dir / f.name):
            seen.add(f.stem)
            n_corpus += 1

    # Lab 2004 + 2009 fill, skipping any stem already taken by production.
    if not LAB_DECISIONS.is_dir():
        raise SystemExit(f"lab decisions dir missing: {LAB_DECISIONS}")
    for f in sorted(LAB_DECISIONS.glob("*.json")):
        if not f.stem.startswith(LAB_YEAR_PREFIXES):
            continue
        if f.stem in seen:
            continue
        if _link(f, decisions_dir / f.name):
            seen.add(f.stem)
            n_lab += 1

    # Summaries (gold holdings, taxonomy, case_index): one dir symlink.
    if not PROD_SUMMARIES.is_dir():
        raise SystemExit(f"production summaries dir missing: {PROD_SUMMARIES}")
    summaries_link = SLICE_ROOT / "summaries"
    _link(PROD_SUMMARIES, summaries_link)

    total = n_corpus + n_lab
    print(f"slice root:        {SLICE_ROOT}")
    print(f"production (0.4.0): {n_corpus}")
    print(f"lab 2004/2009 (0.2.0): {n_lab}")
    print(f"total decisions:   {total}")
    print(f"summaries:         {summaries_link} -> {PROD_SUMMARIES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
