"""In-RAM data store: indexes (Engine) + served records + metadata.

A single ``store`` is loaded once at app startup. When ``R2_INDEX_BASE_URL`` is
set and the local artifacts are missing, ``Store.load`` downloads them from R2
(Railway's filesystem is ephemeral) before constructing the Engine. Everything
served by the API comes from here: the search Engine, the per-case served
records, and the corpus metadata/facets.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from backend.config import settings
from backend.search.engine import COLLECTIONS, Engine

logger = logging.getLogger(__name__)

# Default baseline district win-rate, used if metadata is missing the stat.
DEFAULT_BASELINE = 0.79


def _normalize_case_no(case_no):
    """Accept a case number with or without a leading 'N' and return the key
    form used by records.json (the served records key on the bare oah_case_no,
    which itself includes the N). We try both at lookup time, so just strip
    whitespace here."""
    return (case_no or "").strip()


class Store:
    def __init__(self):
        self.engine = None
        self.records = {}     # case_no -> served record dict
        self.metadata = {}    # corpus metadata / facets dict
        self._records_lower = {}  # lowercased-no-N key -> case_no, for tolerant lookup

    # ------------------------------------------------------------------ #
    def load(self):
        """Download artifacts if needed, then construct the Engine and load
        records + metadata into RAM. Safe to call once at startup."""
        index_dir = Path(settings.INDEX_DIR)
        records_path = Path(settings.RECORDS_PATH)
        metadata_path = Path(settings.METADATA_PATH)

        self._download_if_missing(index_dir, records_path, metadata_path)

        # Engine is load-only; missing collections are tolerated inside Engine.
        self.engine = Engine(
            index_dir,
            embed_backend=settings.EMBED_BACKEND,
            settings=settings,
        )
        logger.info(
            "Engine loaded from %s (embed_backend=%s)",
            index_dir, settings.EMBED_BACKEND,
        )

        self.records = self._load_json(records_path, default={})
        self.metadata = self._load_json(metadata_path, default={})

        # Build a tolerant lookup index (lowercased, leading 'N' stripped).
        self._records_lower = {}
        for case_no in self.records:
            self._records_lower[self._lookup_key(case_no)] = case_no

        stats = (self.metadata or {}).get("corpus_stats") or {}
        logger.info(
            "Store loaded: %d records, %d decisions, %d holdings",
            len(self.records),
            stats.get("n_decisions", 0),
            stats.get("n_holdings", 0),
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _lookup_key(case_no):
        s = (case_no or "").strip().lower()
        if s.startswith("n"):
            s = s[1:]
        return s

    @staticmethod
    def _load_json(path, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("Could not load %s (%s) — using default", path, e)
            return default

    def _download_if_missing(self, index_dir, records_path, metadata_path):
        base = settings.R2_INDEX_BASE_URL.rstrip("/") if settings.R2_INDEX_BASE_URL else ""
        if not base:
            return

        index_dir.mkdir(parents=True, exist_ok=True)
        records_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        # (remote-relative-path, local-path)
        targets = [
            (f"indexes/{col}.pkl", index_dir / f"{col}.pkl") for col in COLLECTIONS
        ]
        targets.append(("records.json", records_path))
        targets.append(("metadata.json", metadata_path))

        with httpx.Client(follow_redirects=True, timeout=300.0) as client:
            for remote, local in targets:
                if local.exists():
                    logger.info("Artifact already present: %s", local)
                    continue
                url = f"{base}/{remote}"
                logger.info("Downloading %s -> %s", url, local)
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    local.write_bytes(resp.content)
                except httpx.HTTPError as e:
                    # A missing collection is non-fatal; the Engine tolerates it.
                    logger.warning("Failed to download %s (%s)", url, e)

    # ------------------------------------------------------------------ #
    def get_record(self, case_no):
        """Return the served record for a case number (with or without the
        leading 'N'), or None."""
        key = _normalize_case_no(case_no)
        rec = self.records.get(key)
        if rec is not None:
            return rec
        return self.records.get(self._records_lower.get(self._lookup_key(key)))

    def baseline(self):
        """Corpus-wide district win-rate baseline (float)."""
        stats = (self.metadata or {}).get("corpus_stats") or {}
        val = stats.get("baseline_district_win_rate")
        try:
            return float(val) if val is not None else DEFAULT_BASELINE
        except (ValueError, TypeError):
            return DEFAULT_BASELINE


store = Store()
