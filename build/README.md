# Offline build pipeline

Produces the artifacts the backend serves (loaded from Cloudflare R2 at
startup): the three search indexes, `records.json`, `metadata.json`, and the
per-decision source PDFs. Runs offline on the desktop; re-runnable.

Everything writes under `build/output/`:

```
build/output/
  indexes/holdings.pkl
  indexes/gold_holdings.pkl
  indexes/decisions.pkl
  records.json
  metadata.json
  docs/{year}/{stem}.pdf
```

## Corpus slice (CORPUS_ROOT)

The pipeline reads from a staging slice at `build/corpus_slice/`, produced by
`make_slice.py`. It is the corrected replacement for the stale
`cert_layoff_merged` build, unioning the two live sources directly:

- production spine — `cert_layoff_corpus/output/corpus/decisions/*.json`
  (412 records, schema 0.4.0)
- lab fill — `cert_layoff_lab/output/corpus/decisions/{2004,2009}*.json`
  (267 records, schema 0.2.0)

= **679 decisions**, plus the production gold holdings + taxonomy under
`cert_layoff_corpus/output/summaries/` (symlinked into the slice).

Every script honors a `CORPUS_ROOT` env override; absent it, they default to
`build/corpus_slice/`. After `make_slice.py` you do not need to set it.

## Prerequisites

```bash
pip install -r build/requirements.txt            # numpy, rank-bm25
# optional, only for embeddings (build_index.py --embed):
pip install -r build/requirements-embed.txt       # sentence-transformers, torch
```

- `convert_docs.py` needs **LibreOffice** (`soffice` on PATH). Fedora:
  `sudo dnf install libreoffice-headless`; Debian/Ubuntu:
  `sudo apt install libreoffice --no-install-recommends`.
- `upload_r2.py` needs the **wrangler** CLI (`npm i -g wrangler`, or the default
  `npx wrangler`) authenticated to your Cloudflare account.

## Run order

```bash
# 1. Stage the slice (symlinks only — fast, no deps). Prints counts.
python build/make_slice.py

# 2. Build search indexes. v1 default is BM25-only (--no-embed); no torch.
python build/build_index.py                # BM25-only (default)
#   python build/build_index.py --embed    # also build arctic-l-v2 vectors

# 3. Build served records + metadata (de-identified; roster names dropped).
#    Set R2_DOC_BASE_URL so records carry a real pdf_url (else null).
R2_DOC_BASE_URL=https://<r2-public-host> python build/build_records.py

# 4. Convert each decision's source doc to a per-decision PDF (LibreOffice).
python build/convert_docs.py               # --limit N for a smoke test

# 5. Upload everything to R2 (wrangler).
R2_BUCKET=<your-bucket> python build/upload_r2.py
#   python build/upload_r2.py --dry-run    # preview keys without uploading
```

## Artifact contracts (summary)

- **indexes/*.pkl** — each a dict: `hash, collection, model_id, ids, texts,
  metas, tokens, emb`. `emb` is a float32 ndarray only when built with
  `--embed`; otherwise `None` (the v1 default → backend forces BM25-only).
- **records.json** — `{ case_no: served_record }`. All served text is
  de-identified at build time; roster names are dropped (only `n_respondents`
  kept). `pdf_url = $R2_DOC_BASE_URL + /docs/{year}/{stem}.pdf` (or null).
- **metadata.json** — `corpus_stats` (incl. `baseline_district_win_rate` over
  all holdings), `taxonomy`, `facets`.

## Notes

- Pickles are content-hashed over `(ids, texts, model_id)` and written
  atomically; an unchanged corpus/model reuses the existing pickle. `--force`
  rebuilds anyway.
- Year is derived robustly: `stem[:4]` when it's a clean 19xx/20xx year, else
  `identity.decision_date[:4]`, else `identity.school_year_affected[:4]`.
- De-identification (`corpuslib/deident.py`) is copied verbatim from the
  validated playground implementation. The original PDFs on R2 retain names
  (acceptable per the relaxed-privacy stance); the served JSON layer does not.
```
