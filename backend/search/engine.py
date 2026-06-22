"""Load-only hybrid search engine: BM25 + (optional) embedding cosine, RRF-fused.

This is a runtime port of the reference engine in
``cert_layoff_playground/prototypes/01-search-mcp/engine.py``. Unlike the
reference it never builds or rebuilds an index and has NO corpus dependency:
it loads pre-built pickles (produced by the offline ``build/`` pipeline and
shipped via R2) and serves over them in RAM.

Filters PRE-restrict the candidate set (not a post-filter of top-k), so a
filtered query still returns k results when matches exist. Fusion is
Reciprocal Rank Fusion with k=60, identical to the reference.

Embeddings are used ONLY when ``embed_backend`` is "arctic" or "openai" AND
the loaded index actually carries an embedding matrix (``emb`` is not None).
The v1 default build is BM25-only (``emb`` is None), so the engine forces
BM25-only mode regardless of the requested mode. The embedding encoder import
is lazy and guarded so the app boots fine with neither torch nor openai
installed.
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

RRF_K = 60

# Collections persisted by the offline build. Fixed, model-independent names.
COLLECTIONS = ("holdings", "gold_holdings", "decisions")

# Arctic model card: query prefix only (no doc prefix). Matches build_index.py.
_ARCTIC_HF_ID = "Snowflake/snowflake-arctic-embed-l-v2.0"
_ARCTIC_QUERY_PREFIX = "query: "
_ARCTIC_MAX_SEQ = 1024
_OPENAI_MODEL = "text-embedding-3-small"


def tokenize(text):
    """Lowercase alnum tokenization — identical to the build-time tokenizer."""
    return re.findall(r"[a-z0-9]+", (text or "").lower())


class Engine:
    """Load pre-built indexes and serve hybrid/BM25 search over them."""

    def __init__(self, index_dir, embed_backend="none", settings=None):
        self.index_dir = Path(index_dir)
        self.embed_backend = (embed_backend or "none").lower()
        self.settings = settings
        self._idx = {}        # collection -> index dict
        self._bm25 = {}       # collection -> BM25Okapi
        self._encoder = None  # lazily-loaded query encoder (ST model or openai client)

        for col in COLLECTIONS:
            path = self.index_dir / f"{col}.pkl"
            if not path.exists():
                # Tolerate a missing collection; it simply won't be searchable.
                continue
            with open(path, "rb") as f:
                idx = pickle.load(f)
            self._idx[col] = idx
            # Build BM25 at load time from the persisted tokens.
            self._bm25[col] = BM25Okapi(idx.get("tokens") or [])

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _has_emb(self, collection):
        idx = self._idx.get(collection) or {}
        return idx.get("emb") is not None

    def _resolve_mode(self, collection, mode):
        """Force BM25-only when embeddings are unavailable or backend is off."""
        if self.embed_backend == "none":
            return "bm25"
        if not self._has_emb(collection):
            return "bm25"
        return mode or "hybrid"

    def _candidates(self, collection, filters):
        idx = self._idx[collection]
        metas = idx["metas"]
        if not filters:
            return np.arange(len(metas))
        keep = [i for i, m in enumerate(metas) if _match(m, filters)]
        return np.asarray(keep, dtype=int)

    def _encode_query(self, query):
        """Lazily load the configured encoder and embed one query vector.

        Imports are guarded so this is only reached when embed_backend is
        arctic/openai AND the index carries embeddings.
        """
        if self.embed_backend == "arctic":
            if self._encoder is None:
                from sentence_transformers import SentenceTransformer  # lazy
                m = SentenceTransformer(_ARCTIC_HF_ID)
                m.max_seq_length = _ARCTIC_MAX_SEQ
                self._encoder = m
            v = self._encoder.encode(
                [_ARCTIC_QUERY_PREFIX + query], normalize_embeddings=True
            )
            return np.asarray(v[0], dtype="float32")

        if self.embed_backend == "openai":
            if self._encoder is None:
                from openai import OpenAI  # lazy
                key = getattr(self.settings, "OPENAI_API_KEY", "") if self.settings else ""
                self._encoder = OpenAI(api_key=key) if key else OpenAI()
            resp = self._encoder.embeddings.create(model=_OPENAI_MODEL, input=query)
            v = np.asarray(resp.data[0].embedding, dtype="float32")
            n = np.linalg.norm(v)
            return v / n if n else v

        raise RuntimeError(f"no embedding encoder for backend {self.embed_backend!r}")

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    EMB_ADMIT = 50  # in hybrid, semantic-only docs admitted from the cosine top-N

    @staticmethod
    def _hit(idx, di, score):
        return {
            "id": idx["ids"][di],
            "score": round(float(score), 5),
            "meta": idx["metas"][di],
            "text": idx["texts"][di],
        }

    def search(self, collection, query, filters=None, k=10, mode="hybrid",
               min_ratio=0.0):
        """Return results as a list of {id, score, meta, text}.

        Two modes by intent:
        - BROWSE (empty query): the match set is exactly the filtered candidates
          (BM25 over an empty query is all-zero and meaningless). Returned in
          corpus order; the caller orders them (e.g. by recency).
        - QUERY (non-empty): only docs the query actually hits are results — the
          zero-overlap tail is dropped (it would inflate totals and dilute the
          insight strip). ``min_ratio`` (0..1) optionally gates further, keeping
          only docs whose BM25 score is >= min_ratio * max BM25 score, which
          trims weak single-common-term matches. The top match always passes.

        ``k`` caps the number returned; pass ``k=None`` for the full set (cheap
        at this corpus size, and required for exact totals/insight upstream).
        """
        idx = self._idx.get(collection)
        if idx is None:
            return []
        cand = self._candidates(collection, filters)
        if len(cand) == 0:
            return []

        mode = self._resolve_mode(collection, mode)
        query = (query or "").strip()

        # Browse: no relevance signal — return the filtered candidate set as-is.
        if not query:
            chosen = cand if k is None else cand[:k]
            return [self._hit(idx, int(di), 0.0) for di in chosen]

        ranks = {}     # doc index -> list of per-signal ranks
        matched = set()  # docs with genuine relevance in at least one signal

        if mode in ("hybrid", "bm25"):
            scores = np.asarray(self._bm25[collection].get_scores(tokenize(query)))
            cand_scores = scores[cand]
            mx = float(cand_scores.max()) if len(cand_scores) else 0.0
            if mx <= 0:
                hit_mask = np.zeros(len(cand), dtype=bool)
            elif min_ratio > 0:
                hit_mask = cand_scores >= (mx * min_ratio)
            else:
                hit_mask = cand_scores > 0
            hit_cand = cand[hit_mask]
            order = hit_cand[np.argsort(-scores[hit_cand], kind="stable")]
            for r, di in enumerate(order):
                di = int(di)
                ranks.setdefault(di, []).append(r)
                matched.add(di)

        if mode in ("hybrid", "embed"):
            qv = self._encode_query(query)
            sims = idx["emb"][cand] @ qv
            order = cand[np.argsort(-sims, kind="stable")]
            # Embeddings only contribute ranks to existing lexical matches, or to
            # the cosine top-N (semantic recall) — never to the meaningless tail.
            for r, di in enumerate(order):
                di = int(di)
                if di in matched or r < self.EMB_ADMIT:
                    ranks.setdefault(di, []).append(r)
                    matched.add(di)

        fused = sorted(
            ((sum(1.0 / (RRF_K + r) for r in rs), di) for di, rs in ranks.items()),
            key=lambda t: -t[0],
        )
        chosen = fused if k is None else fused[:k]
        return [self._hit(idx, di, score) for score, di in chosen]

    def list_facets(self, collection):
        """Value counts over a collection's metas, ported from the reference.

        ``categories`` (list, gold) is folded into the ``category`` slot.
        Returns {facet_key: {value: count}} sorted descending by count.
        """
        idx = self._idx.get(collection)
        if idx is None:
            return {}
        facets = {}
        for m in idx["metas"]:
            for key in ("year", "category", "categories", "district", "alj",
                        "prevailing_party", "overall"):
                v = m.get(key)
                if v is None:
                    continue
                vals = v if isinstance(v, list) else [v]
                slot_key = "category" if key == "categories" else key
                slot = facets.setdefault(slot_key, {})
                for x in vals:
                    if x in (None, ""):
                        continue
                    slot[x] = slot.get(x, 0) + 1
        return {
            k: dict(sorted(v.items(), key=lambda t: -t[1]))
            for k, v in facets.items()
        }


def _match(meta, filters):
    """AND-combine filters against one meta dict. Ported verbatim from the
    reference engine: substring district/ALJ (raw + canonical + gold cites),
    exact year (string-compared), category-in-list, exact otherwise."""
    for key, want in filters.items():
        if want in (None, ""):
            continue
        if key == "year":
            if str(meta.get("year")) != str(want):
                return False
        elif key == "category":
            cats = meta.get("categories")
            if cats is not None:
                if want not in cats:
                    return False
            elif meta.get("category") != want:
                return False
        elif key in ("district", "alj"):
            # substring, case-insensitive: district/ALJ strings are raw and
            # un-canonicalized (spelling variants exist).
            w = str(want).lower()
            own = " ".join(str(meta.get(f) or "") for f in (key, f"{key}_raw")).lower()
            cites = meta.get("cites") or []
            cite_vals = " ".join(str(c.get(key) or "") for c in cites).lower()
            if w not in own and w not in cite_vals:
                return False
        else:
            if meta.get(key) != want:
                return False
    return True
