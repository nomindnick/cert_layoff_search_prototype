#!/usr/bin/env python3
"""Analytics digest from the events log (PLAN.md §8).

The events table is the project's highest-value byproduct: product usage, a
leakage-free eval relevance pool, and training signal. There is no in-app admin
dashboard yet, so this prints a readable digest straight from Postgres.

Connection (in priority order):
  1. ANALYTICS_DB_URL env var, or
  2. the Railway Postgres public URL, auto-discovered via the `railway` CLI
     (`railway variables --service Postgres`). Requires you be logged in.

Person names are resolved from the app's ACCESS_TOKENS (also via the CLI).

Run:  ./.venv/bin/python scripts/analytics.py [--recent N]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


def _railway_kv(service: str) -> dict:
    exe = shutil.which("railway")
    if not exe:
        return {}
    try:
        out = subprocess.run(
            [exe, "variables", "--service", service, "--kv"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    kv = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            kv[k.strip()] = v.strip()
    return kv


def _db_url() -> str:
    url = os.environ.get("ANALYTICS_DB_URL")
    if not url:
        url = _railway_kv("Postgres").get("DATABASE_PUBLIC_URL", "")
    if not url:
        sys.exit("No DB URL. Set ANALYTICS_DB_URL or log in to the Railway CLI "
                 "(railway login) so the Postgres public URL can be discovered.")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def _names() -> dict:
    raw = _railway_kv("cert-layoff-search").get("ACCESS_TOKENS", "")
    names = {}
    for entry in raw.split(","):
        tok, _, name = entry.strip().partition(":")
        if tok.strip():
            names[tok.strip()] = name.strip() or tok.strip()
    return names


def _hr(title: str):
    print(f"\n\033[1m{title}\033[0m")
    print("─" * len(title))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent", type=int, default=15, help="rows in the recent-activity feed")
    args = ap.parse_args()

    import psycopg

    names = _names()
    label = lambda t: names.get(t, t or "(anonymous)")  # noqa: E731

    with psycopg.connect(_db_url()) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), min(ts), max(ts) FROM events")
        total, first, last = cur.fetchone()
        _hr("Overview")
        print(f"  {total} events  ·  {first:%Y-%m-%d} → {last:%Y-%m-%d}" if total else "  no events yet")
        if not total:
            return 0

        _hr("Per person")
        cur.execute("""
            SELECT user_token,
                   count(*)                              AS events,
                   count(DISTINCT session_id)            AS sessions,
                   count(DISTINCT date(ts))              AS active_days,
                   count(DISTINCT ip_hash)               AS ips,
                   count(DISTINCT referrer)              AS referrers,
                   max(ts)                               AS last_seen
            FROM events GROUP BY user_token ORDER BY events DESC
        """)
        for tok, ev, sess, days, ips, refs, seen in cur.fetchall():
            share = "  ⚠ multiple IPs (link may be shared/forwarded)" if (ips or 0) > 1 else ""
            print(f"  {label(tok):<16} {ev:>4} events · {sess} sessions · {days} active days · "
                  f"last {seen:%b %d}{share}")

        _hr("Activity by type")
        cur.execute("SELECT event_type, count(*) FROM events GROUP BY event_type ORDER BY count(*) DESC")
        for et, n in cur.fetchall():
            print(f"  {et:<16} {n}")

        _hr("Top searches")
        cur.execute("""
            SELECT query, count(*) FROM events
            WHERE event_type='search' AND query IS NOT NULL AND query <> ''
            GROUP BY query ORDER BY count(*) DESC LIMIT 15
        """)
        rows = cur.fetchall()
        if rows:
            for q, n in rows:
                print(f"  {n:>3}×  {q}")
        else:
            print("  (no text searches logged yet)")

        _hr("Click-through (the relevance/eval pool)")
        cur.execute("SELECT count(*) FROM events WHERE event_type='search'")
        searches = cur.fetchone()[0]
        cur.execute("""SELECT count(*), avg(rank) FROM events
                       WHERE event_type IN ('expand_holding','open_decision','download_pdf')""")
        clicks, avg_rank = cur.fetchone()
        print(f"  {searches} searches → {clicks} result clicks"
              + (f" · avg clicked rank {avg_rank:.1f}" if avg_rank else ""))

        _hr(f"Recent activity (last {args.recent})")
        cur.execute("""
            SELECT ts, user_token, event_type, coalesce(query, target_id, '')
            FROM events ORDER BY ts DESC LIMIT %s
        """, (args.recent,))
        for ts, tok, et, what in cur.fetchall():
            print(f"  {ts:%m-%d %H:%M}  {label(tok):<14} {et:<15} {what[:60]}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
