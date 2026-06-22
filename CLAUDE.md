# CLAUDE.md

Guidance for working in this repo. **Read `PLAN.md` first — it is the authoritative build
guide.** This file is the quick orientation + the conventions that are easy to get wrong.

## What this is
A search + insight web app over the firm's corpus of California OAH proposed decisions on
certificated (teacher) layoffs. Audience: essentially one L&E attorney. Goal: a concrete,
visually compelling "glimpse of what's possible." Status: greenfield — only `PLAN.md` and
this file exist so far. Build it per `PLAN.md §13`.

## The thesis (don't lose this)
The corpus's value is **structured signal on obscure non-precedential holdings that exist
nowhere else** — who wins, on what issue, before which ALJ, trending which way — every claim
traceable to a real decision. **The UI does the analytical work.** Lead with structured
retrieval + analytics + deterministic reports. **Not a chatbot.**

## Locked decisions
- v1 = **insight dashboard + deterministic report generator**.
- Hosting = **Railway** (app) + **Cloudflare R2** (indexes + source docs).
- Access = **per-person magic links** (token = auth + analytics user id + share-detector).
- **No generative AI in v1.** LLM report-summary deferred to v2.
- Embeddings = **arctic-l-v2** (`Snowflake/snowflake-arctic-embed-l-v2.0`) on CPU.
- Corpus slice ≈ **666 decisions** (see below) + 5,608 gold holdings.

## Critical conventions (easy to get wrong)
- **Primary search unit is the *holding*, not the document** — grouped by decision in the UI.
- **De-identify at index-build time** (respondent names never enter the search index — the
  result layer is "District (ALJ)"-safe). Source PDFs + the in-app `full_text` reader retain
  names — that's acceptable (relaxed privacy, public records). Keep a name-scrub gate
  available but off.
- **Win-rate is skewed ~79% district** — always show it per-issue *against the corpus
  baseline*, never as a bare percentage.
- **Log analytics from day one** — every search logs the query + ranked `shown` ids; every
  click/open/download logs the target. This is the project's highest-value byproduct
  (eval + training signal). See `PLAN.md §8`.
- **No generative answers** — naive RAG hurts usefulness/correctness here (measured).
- **Don't expose raw relevance scores** to the client; rank only.

## Data slice (see `PLAN.md §4`)
- Spine: `cert_layoff_corpus/output/corpus/decisions/` — **412 decisions, all v0.4.0**.
- Union in: lab `cert_layoff_lab/output/corpus/decisions/` **2004 + 2009 only** (254, v0.2.0).
- **Do NOT use `cert_layoff_merged`** — it's stale (old 174-record build).
- Load via `cert_layoff_playground/corpuslib/corpus.py` (schema-tolerant; derives year from
  the OAH case-number prefix when `decision_date` is null). Don't access raw schema fields
  assuming v0.4.0 — tolerate the v0.2/v0.4 mix.

## Reuse, don't reinvent (exact paths)
- Hybrid search engine + index build:
  `cert_layoff_playground/prototypes/01-search-mcp/{engine.py, build_index.py}`
- Corpus loader + de-id: `cert_layoff_playground/corpuslib/{corpus.py, deident.py}`
- Deterministic reports: `cert_layoff_corpus/pipeline/render_summary.py` + `REPORTS.md`
- ALJ scouting (v1.5): `cert_layoff_playground/prototypes/03-alj-scouting/`
- App skeleton (routers, lifespan, R2 download, SPA serving): `fppc-opinions-app/backend/`
- Eval harness: `fppc-opinions-eval/src/scorer.py`
- Schema reference: `cert_layoff_corpus/schema/decision_record.schema.json`

## Intended layout & commands (once built — see `PLAN.md §11`)
```
backend/   FastAPI (serves API + the built SPA)
frontend/  Vite + React 19 + Tailwind
build/     offline: build_index.py, convert_docs.py, upload_r2.py  (run on the desktop)
```
- Offline build (desktop): `python build/build_index.py` then `python build/upload_r2.py`
- Backend dev: `uvicorn backend.main:app --reload`
- Frontend dev: `cd frontend && npm run dev` (proxy `/api` → localhost:8000)
- Source-doc conversion: LibreOffice headless (`soffice --headless --convert-to pdf`)

## Gotchas from prior repos
- ollama/local-model quirks live in the lab repos; this app does **not** call ollama at
  query time (static, pre-built indexes — the FPPC pattern).
- Real `sk-proj-...` OpenAI keys sit gitignored in the FPPC repos — do not copy `.env`
  files; start fresh and gitignore secrets.
- Railway filesystem is ephemeral — download indexes from R2 at startup; never commit pickles.
