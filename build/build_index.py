#!/usr/bin/env python3
"""Build the three search indexes for the app, ported from the reference
prototype build_index.py (cert_layoff_playground/prototypes/01-search-mcp).

Differences from the reference, per the build contract:
  (a) imports the vendored corpuslib from build/ (this dir on sys.path),
  (b) reads CORPUS_ROOT=build/corpus_slice (set here if not already in env),
  (c) writes FIXED, model-independent filenames:
        build/output/indexes/holdings.pkl
        build/output/indexes/gold_holdings.pkl
        build/output/indexes/decisions.pkl
  (d) --no-embed (default ON for v1) skips embedding and leaves emb=None,
  (e) arctic-l-v2 is the model when embeddings ARE built,
  (f) robust year derivation: stem[:4] if 19xx/20xx, else identity.decision_date[:4],
      else identity.school_year_affected[:4].

Each pickle is a dict: hash, collection, model_id, ids, texts, metas, tokens, emb.
emb is a float32 ndarray when embeddings were built, else None (v1 default).
Pickles are keyed by a content hash of (ids, texts, model_id) and written
atomically; an unchanged corpus/model reuses the existing pickle.

Usage:
  build_index.py                 # BM25-only (v1 default, no torch needed)
  build_index.py --embed         # also build arctic-l-v2 embeddings
  build_index.py --force         # rebuild even if the content hash matches
"""

import argparse
import hashlib
import json
import os
import pickle
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # vendored corpuslib lives in build/

# Point the loader at the staging slice unless the caller overrode it.
os.environ.setdefault("CORPUS_ROOT", str(HERE / "corpus_slice"))

from corpuslib import load_decisions, load_gold_holdings  # noqa: E402
from corpuslib.deident import alj_surname, deidentify, district_short  # noqa: E402

OUT = HERE / "output" / "indexes"

# arctic-l-v2 won the embedding bench in fppc-tuned-embeddings (MRR 0.522,
# above the OpenAI baseline). Prefix per the model card — queries only.
MODELS = {
    "arctic-l-v2": {
        "hf_id": "Snowflake/snowflake-arctic-embed-l-v2.0",
        "query_prefix": "query: ",
        "doc_prefix": "",
        "max_seq": 1024,
    },
}
DEFAULT_MODEL = "arctic-l-v2"

EMBEDDED_COLLECTIONS = ("holdings", "gold_holdings")

_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")


def tokenize(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def derive_year(stem, rec):
    """Robust year for a decision: stem prefix if it's a clean 19xx/20xx year,
    else identity.decision_date[:4], else identity.school_year_affected[:4].
    Returns a 4-char string or "" when nothing resolves."""
    prefix = (stem or "")[:4]
    if _YEAR_RE.match(prefix):
        return prefix
    ident = rec.get("identity") or {}
    date = ident.get("decision_date") or ""
    if _YEAR_RE.match(date[:4]):
        return date[:4]
    sy = ident.get("school_year_affected") or ""
    if _YEAR_RE.match(sy[:4]):
        return sy[:4]
    return ""


def holding_text(h):
    """The searchable composition for one extracted holding: issue statement +
    house-style paragraph + reasoning summary."""
    parts = [
        (h.get("issue") or {}).get("statement"),
        h.get("summary_style_holding"),
        (h.get("reasoning") or {}).get("summary"),
    ]
    return " ".join(p.strip() for p in parts if p)


def build_holdings_docs():
    ids, texts, metas = [], [], []
    for stem, rec in load_decisions():
        ident = rec.get("identity") or {}
        case_no = ident.get("oah_case_no") or stem
        district_raw = (ident.get("district") or {}).get("raw") or ""
        alj_raw = (ident.get("alj") or {}).get("raw") or ""
        outcome = rec.get("outcome") or {}
        year = derive_year(stem, rec)
        for i, h in enumerate(rec.get("holdings") or []):
            text = holding_text(h)
            if not text:
                continue
            # privacy by construction: respondent names never enter the index,
            # so search results/snippets are District (ALJ)-safe everywhere.
            text, _ = deidentify(text, rec)
            summary, _ = deidentify(h.get("summary_style_holding") or "", rec)
            statement, _ = deidentify((h.get("issue") or {}).get("statement") or "", rec)
            ids.append(f"{case_no}:{i}")
            texts.append(text)
            metas.append({
                "case_no": case_no,
                "holding_idx": i,
                "year": year,
                "category": (h.get("issue") or {}).get("category"),
                "subtype": (h.get("issue") or {}).get("subtype"),
                "statement": statement,
                "district": district_short(district_raw),
                "district_raw": district_raw,
                "alj": alj_surname(alj_raw),
                "alj_raw": alj_raw,
                "prevailing_party": (h.get("ruling") or {}).get("prevailing_party"),
                "remedies": (h.get("ruling") or {}).get("remedies") or [],
                "overall": outcome.get("overall"),
                "decision_kind": ident.get("decision_kind"),
                "summary": summary,
            })
    return ids, texts, metas


def build_gold_docs():
    ids, texts, metas = [], [], []
    for i, h in enumerate(load_gold_holdings()):
        # rows with no category_raw are volume headers/front-matter, not holdings
        if not h.get("category_raw"):
            continue
        text = (h.get("text") or "").strip()
        if not text:
            continue
        ids.append(f"g{i}")
        texts.append(text)
        metas.append({
            "year": str(h.get("sort_year") or ""),
            "categories": h.get("category_canonical") or [],
            "letter_title": h.get("letter_title"),
            "cites": h.get("cites") or [],
            "volume": h.get("volume"),
            "summary": text,
        })
    return ids, texts, metas


def build_decision_docs():
    ids, texts, metas = [], [], []
    for stem, rec in load_decisions():
        ident = rec.get("identity") or {}
        case_no = ident.get("oah_case_no") or stem
        district_raw = (ident.get("district") or {}).get("raw") or ""
        alj_raw = (ident.get("alj") or {}).get("raw") or ""
        # de-identify the full text that feeds the BM25 decisions index — the
        # served full_text is de-identified at build_records time too.
        full_text, _ = deidentify(rec.get("full_text") or "", rec)
        ids.append(case_no)
        texts.append(full_text)
        metas.append({
            "case_no": case_no,
            "year": derive_year(stem, rec),
            "district": district_short(district_raw),
            "district_raw": district_raw,
            "alj": alj_surname(alj_raw),
            "alj_raw": alj_raw,
            "overall": (rec.get("outcome") or {}).get("overall"),
            "decision_kind": ident.get("decision_kind"),
            "n_holdings": len(rec.get("holdings") or []),
        })
    return ids, texts, metas


BUILDERS = {
    "holdings": build_holdings_docs,
    "gold_holdings": build_gold_docs,
    "decisions": build_decision_docs,
}


def content_hash(ids, texts, model_id):
    h = hashlib.sha1()
    h.update(json.dumps([ids, texts], sort_keys=True).encode())
    h.update(model_id.encode())
    return h.hexdigest()


def index_path(collection):
    """Fixed, model-independent filename per the build contract."""
    return OUT / f"{collection}.pkl"


def build_or_load(collection, model_key=DEFAULT_MODEL, embed=False,
                  force=False, st_model=None):
    """Return the index dict for a collection, building it if stale/missing.

    With embed=False (v1 default) emb is None even for embeddable collections,
    so the build needs neither torch nor sentence-transformers.
    """
    cfg = MODELS[model_key]
    ids, texts, metas = BUILDERS[collection]()
    do_embed = embed and collection in EMBEDDED_COLLECTIONS
    model_id = cfg["hf_id"] if do_embed else "none"
    chash = content_hash(ids, texts, model_id)
    path = index_path(collection)
    if path.exists() and not force:
        with open(path, "rb") as f:
            idx = pickle.load(f)
        if idx.get("hash") == chash:
            print(f"[{collection}] up to date ({len(ids)} docs) — reused")
            return idx
        print(f"[{collection}] stale index (corpus/model changed) — rebuilding")
    idx = {
        "hash": chash,
        "collection": collection,
        "model_id": model_id,
        "ids": ids,
        "texts": texts,
        "metas": metas,
        "tokens": [tokenize(t) for t in texts],
        "emb": None,
    }
    if do_embed:
        import numpy as np
        if st_model is None:
            st_model = load_st_model(model_key)
        print(f"[{collection}] embedding {len(texts)} docs with {cfg['hf_id']} ...")
        emb = st_model.encode(
            [cfg["doc_prefix"] + t for t in texts],
            batch_size=16, show_progress_bar=True, normalize_embeddings=True,
        )
        idx["emb"] = np.asarray(emb, dtype="float32")
    OUT.mkdir(parents=True, exist_ok=True)
    # atomic write: a concurrent reader never sees a half-written pickle
    tmp = path.with_suffix(".pkl.tmp")
    with open(tmp, "wb") as f:
        pickle.dump(idx, f)
    tmp.replace(path)
    emb_note = "with embeddings" if do_embed else "BM25-only"
    print(f"[{collection}] built: {len(ids)} docs ({emb_note}) -> {path.name}")
    return idx


def load_st_model(model_key=DEFAULT_MODEL):
    from sentence_transformers import SentenceTransformer
    cfg = MODELS[model_key]
    m = SentenceTransformer(cfg["hf_id"])
    m.max_seq_length = cfg["max_seq"]
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=DEFAULT_MODEL, choices=list(MODELS))
    # --no-embed is the default for v1 (kept as an explicit flag for clarity);
    # --embed opts in to building arctic-l-v2 vectors.
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--no-embed", dest="embed", action="store_false",
                   help="BM25-only build (default)")
    g.add_argument("--embed", dest="embed", action="store_true",
                   help="also build arctic-l-v2 embeddings")
    ap.set_defaults(embed=False)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    st = load_st_model(args.model) if args.embed else None
    for c in BUILDERS:
        build_or_load(c, args.model, embed=args.embed, force=args.force,
                      st_model=st)
    print(f"indexes written to {OUT}")


if __name__ == "__main__":
    main()
