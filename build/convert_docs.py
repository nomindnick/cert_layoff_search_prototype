#!/usr/bin/env python3
"""Convert each decision's source document to a per-decision PDF for the
"Download original" button.

For every decision record, take provenance.source_files[0].path (a relative
path like "download (5)/Live Oak USD 1999020316.PDF"), locate it under one of
the Cert_Layoffs_Docs_V1 source trees, and produce:

    build/output/docs/{year}/{stem}.pdf

where stem is the decision's filename stem (year-prefixed, no "N") and year is
the robust-derived year. Native PDFs are copied; RTF/DOC/DOCX are converted via
LibreOffice headless ("soffice --headless --convert-to pdf").

REQUIREMENTS: LibreOffice must be installed and `soffice` on PATH (Fedora:
`sudo dnf install libreoffice-headless`; Debian/Ubuntu: `apt install
libreoffice --no-install-recommends`). Without it, only already-PDF sources are
copied and the rest are skipped with a logged warning.

Defensive throughout: a missing source file, a failed conversion, or a record
with no source_files is logged and skipped — never fatal.

Usage:
  python build/convert_docs.py                 # convert all
  python build/convert_docs.py --limit 20      # first 20 (smoke test)
  python build/convert_docs.py --force         # re-convert even if PDF exists
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

os.environ.setdefault("CORPUS_ROOT", str(HERE / "corpus_slice"))

from corpuslib import load_decisions  # noqa: E402
from build_index import derive_year  # noqa: E402

OUT = HERE / "output" / "docs"

# Source-document trees. Each decision's provenance path is relative to one of
# these roots (e.g. "download (5)/...").
DOC_TREES = [
    Path("/home/nick/Projects/cert_layoff_corpus/Cert_Layoffs_Docs_V1"),
    Path("/home/nick/Projects/cert_layoff_lab/Cert_Layoffs_Docs_V1"),
]

PDF_EXTS = {".pdf"}


def has_soffice():
    return shutil.which("soffice") is not None


def locate_source(rel_path):
    """Resolve a provenance-relative source path against the doc trees.
    Returns a Path or None. Tries the exact relative path first, then a
    basename search as a fallback (path drift between repos)."""
    rel = (rel_path or "").strip()
    if not rel:
        return None
    for tree in DOC_TREES:
        cand = tree / rel
        if cand.is_file():
            return cand
    # fallback: match by basename anywhere under the trees
    name = Path(rel).name
    for tree in DOC_TREES:
        if not tree.is_dir():
            continue
        for cand in tree.rglob(name):
            if cand.is_file():
                return cand
    return None


def source_path_for(rec):
    """First provenance.source_files entry's path (str) or None."""
    prov = rec.get("provenance") or {}
    files = prov.get("source_files") or []
    if not files:
        return None
    return (files[0] or {}).get("path")


def convert_to_pdf(src, dst):
    """Convert src -> dst (PDF). PDFs are copied; everything else goes through
    soffice. Returns ("copied"|"converted"|"failed"|"no-soffice", message)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in PDF_EXTS:
        shutil.copyfile(src, dst)
        return "copied", ""
    if not has_soffice():
        return "no-soffice", "soffice not on PATH"
    # soffice writes <stem>.pdf into the outdir; do it in a temp dir then move
    # to the canonical name (source stems don't match our {stem}.pdf naming).
    with tempfile.TemporaryDirectory() as td:
        try:
            proc = subprocess.run(
                ["soffice", "--headless", "--convert-to", "pdf",
                 "--outdir", td, str(src)],
                capture_output=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            return "failed", "soffice timeout"
        except OSError as e:
            return "failed", f"soffice error: {e}"
        produced = list(Path(td).glob("*.pdf"))
        if proc.returncode != 0 or not produced:
            msg = (proc.stderr or b"").decode(errors="replace").strip()[:200]
            return "failed", msg or f"exit {proc.returncode}, no pdf produced"
        shutil.move(str(produced[0]), str(dst))
    return "converted", ""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0,
                    help="convert only the first N decisions (0 = all)")
    ap.add_argument("--force", action="store_true",
                    help="re-convert even when the target PDF already exists")
    args = ap.parse_args()

    if not has_soffice():
        print("WARNING: soffice (LibreOffice) not found on PATH — only sources "
              "that are already PDF will be copied; RTF/DOC will be skipped.\n"
              "Install LibreOffice headless to convert non-PDF sources.")

    stats = {"copied": 0, "converted": 0, "failed": 0,
             "no-soffice": 0, "missing": 0, "no-source": 0, "skip-exists": 0}
    n = 0
    for stem, rec in load_decisions():
        if args.limit and n >= args.limit:
            break
        n += 1
        year = derive_year(stem, rec) or "unknown"
        dst = OUT / year / f"{stem}.pdf"
        if dst.exists() and not args.force:
            stats["skip-exists"] += 1
            continue
        rel = source_path_for(rec)
        if not rel:
            stats["no-source"] += 1
            print(f"  no source_files: {stem}")
            continue
        src = locate_source(rel)
        if src is None:
            stats["missing"] += 1
            print(f"  missing source: {stem} ({rel})")
            continue
        status, msg = convert_to_pdf(src, dst)
        stats[status] = stats.get(status, 0) + 1
        if status in ("failed", "no-soffice"):
            print(f"  {status}: {stem} ({src.name}) {msg}")

    print("\n=== convert_docs summary ===")
    for k in ("copied", "converted", "skip-exists", "no-source", "missing",
              "failed", "no-soffice"):
        print(f"  {k:12s}: {stats.get(k, 0)}")
    print(f"output dir: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
