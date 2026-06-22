#!/usr/bin/env python3
"""Upload the build artifacts to Cloudflare R2 via wrangler.

Mirrors the R2 layout the backend expects:
    indexes/holdings.pkl, indexes/gold_holdings.pkl, indexes/decisions.pkl
    records.json
    metadata.json
    docs/{year}/{stem}.pdf

Each local artifact under build/output/ is put at the matching key (the key is
the path relative to build/output/). Uploads run via:
    wrangler r2 object put <BUCKET>/<key> --file <path> --remote

Config (env):
    R2_BUCKET            target bucket name (required to actually upload)
    WRANGLER             wrangler invocation (default: "npx wrangler"; set to
                         "wrangler" if installed globally)
    R2_UPLOAD_PARALLEL   parallel workers (default 8)

If wrangler/npx is unavailable, prints setup instructions and exits without
uploading. Use --dry-run to list what WOULD be uploaded.

Usage:
  R2_BUCKET=cert-layoff python build/upload_r2.py
  python build/upload_r2.py --dry-run
  python build/upload_r2.py --skip-docs        # indexes + json only
"""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"

BUCKET = os.environ.get("R2_BUCKET", "")
WRANGLER = os.environ.get("WRANGLER", "npx wrangler")
PARALLEL = int(os.environ.get("R2_UPLOAD_PARALLEL", "8"))


def wrangler_argv():
    """The wrangler command split into argv, or None if unavailable."""
    parts = shlex.split(WRANGLER)
    exe = parts[0]
    if shutil.which(exe) is None:
        return None
    return parts


def collect_artifacts(skip_docs=False):
    """Yield (local_path, r2_key) for every artifact to upload."""
    for name in ("records.json", "metadata.json"):
        p = OUT / name
        if p.is_file():
            yield p, name
    idx_dir = OUT / "indexes"
    if idx_dir.is_dir():
        for p in sorted(idx_dir.glob("*.pkl")):
            yield p, f"indexes/{p.name}"
    if not skip_docs:
        docs_dir = OUT / "docs"
        if docs_dir.is_dir():
            for p in sorted(docs_dir.rglob("*.pdf")):
                yield p, str(p.relative_to(OUT))


def put_one(argv, path, key, dry_run):
    target = f"{BUCKET}/{key}"
    if dry_run:
        return key, True, "(dry-run)"
    cmd = argv + ["r2", "object", "put", target, "--file", str(path), "--remote"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        return key, False, str(e)
    if proc.returncode == 0:
        return key, True, ""
    err = (proc.stderr or b"").decode(errors="replace").strip()[:200]
    return key, False, err


INSTRUCTIONS = """\
wrangler not found. To upload to Cloudflare R2:

  1. Install Node 18+ and the Cloudflare Wrangler CLI:
       npm install -g wrangler      (or use the default `npx wrangler`)
  2. Authenticate:
       wrangler login               (or set CLOUDFLARE_API_TOKEN +
                                     CLOUDFLARE_ACCOUNT_ID in the env)
  3. Set the target bucket and re-run:
       R2_BUCKET=<your-bucket> python build/upload_r2.py

Override the wrangler invocation with WRANGLER="wrangler" if it is installed
globally rather than via npx.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="list artifacts without uploading")
    ap.add_argument("--skip-docs", action="store_true",
                    help="upload indexes + json only (skip docs/**)")
    args = ap.parse_args()

    artifacts = list(collect_artifacts(skip_docs=args.skip_docs))
    if not artifacts:
        print(f"no artifacts found under {OUT} — run the build steps first")
        return 1

    if not args.dry_run:
        if not BUCKET:
            print("R2_BUCKET not set — refusing to upload. "
                  "Set R2_BUCKET=<bucket> or use --dry-run.")
            return 2
        if wrangler_argv() is None:
            print(INSTRUCTIONS)
            return 3

    argv = wrangler_argv() or []
    print(f"{'DRY-RUN: ' if args.dry_run else ''}uploading {len(artifacts)} "
          f"artifacts to bucket '{BUCKET or '(unset)'}' "
          f"({PARALLEL} workers)")

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=max(1, PARALLEL)) as ex:
        futures = [
            ex.submit(put_one, argv, path, key, args.dry_run)
            for path, key in artifacts
        ]
        for fut in futures:
            key, success, msg = fut.result()
            if success:
                ok += 1
                print(f"OK:   {key}")
            else:
                fail += 1
                print(f"FAIL: {key} — {msg}", file=sys.stderr)

    print(f"\ndone: {ok} ok, {fail} failed")
    return 0 if fail == 0 else 4


if __name__ == "__main__":
    raise SystemExit(main())
