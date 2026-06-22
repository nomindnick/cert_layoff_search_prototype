# Cert Layoff Search — Build Plan

A search + insight web app over the firm's corpus of California OAH proposed decisions
on certificated (teacher) layoffs. This document guides the build. Read it fully before
writing code.

---

## 1. Purpose & thesis

**Goal:** put a concrete, visually compelling tool in an L&E partner/associate's hands so
the prior emails about extraction + evals feel real — "a glimpse of what's possible."

**Audience:** essentially one L&E attorney (maybe a few firm attorneys she shares with).
She clicks a link and uses it. No onboarding, no manual.

**Product thesis (the thing that makes this impressive):**
> The corpus's unique value isn't "search" and it is *not* a chatbot. Its value is
> **structured signal on obscure, non-precedential holdings that exist nowhere else** —
> who wins, on what issue, before which ALJ, trending which way — every claim traceable to
> a real decision. **The UI does the analytical work** so the attorney isn't reading
> 8-page PDFs to find the shape of the law on her question.

This thesis is grounded in our own eval work (see `§12 Lessons`): issue-spotting is
near-solved, closed-book citation of these holdings is **0%** for every model including
Opus, and naive RAG buys grounding but *not* usefulness/correctness. So we lean into
**structured retrieval + analytics + deterministic reports**, not generation.

---

## 2. Locked decisions

| Decision | Choice |
|---|---|
| v1 scope | **Insight dashboard + deterministic report generator** |
| Hosting | **Railway** (app) + **Cloudflare R2** (indexes + source docs) |
| Access / identity | **Per-person magic links** (token = auth + user id + share-detector) |
| Generative AI in v1 | **None.** LLM report-summary + report enhancements deferred to v2 |
| Embedding model | **arctic-l-v2** (`Snowflake/snowflake-arctic-embed-l-v2.0`) on CPU |
| Corpus slice | **Production 412 (v0.4.0) ∪ lab 2004+2009 (254, v0.2.0) ≈ 666 decisions** + 5,608 gold holdings |
| Analytics store | **Postgres** (Railway add-on). PostHog optional, later. |

**Non-goals (v1):** no generative Q&A / chatbot, no embedding fine-tuning, no new
extraction (use what's already built). ALJ profiles + issue-explorer landing pages are
**v1.5**; LLM report summaries are **v2**.

---

## 3. Architecture

Reuse the proven FPPC seam (`/home/nick/Projects/fppc-opinions-app`), adding the two
things FPPC deliberately lacked: **auth** and **analytics**.

```
[ OFFLINE BUILD — on the Framework Desktop, free ]
  corpus 412 (v0.4.0) ∪ lab 2004/2009 ──► build_index.py ──► holdings.pkl
        │                                                     gold.pkl
        │                                                     decisions.pkl  (BM25-only)
  source RTF/DOC/PDF  ──► convert_docs.py (LibreOffice headless) ──► per-decision PDF
        │                                                     + clean full_text JSON
        └──────────────────► upload_r2.py ──► Cloudflare R2 (indexes/ + docs/)

[ RAILWAY — one FastAPI service, ~$5–10/mo ]
  FastAPI
    ├─ serves React/Vite/Tailwind SPA (built into the image)
    ├─ downloads *.pkl from R2 at startup (Railway fs is ephemeral) → loads into RAM
    ├─ magic-link middleware (token → user) on every request
    ├─ /api/search  /api/decision  /api/report  /api/facets
    ├─ /api/events  ──► Postgres   (the analytics event log)
    └─ source docs served browser → R2 directly (not proxied)
```

Search is brute-force numpy over a tiny corpus (~thousands of vectors) — instant. No FAISS,
no vector DB.

---

## 4. Data & index build (offline, re-runnable)

### 4.1 Slice
- **Spine:** `cert_layoff_corpus/output/corpus/decisions/*.json` — 412 records, all
  schema **v0.4.0**, years 1999–2003 + 2018–2025.
- **Union in:** the lab's **2004 (62) + 2009 (192)** builds
  (`cert_layoff_lab/output/corpus/decisions/`, schema v0.2.0) for mid-decade coverage.
- **Do NOT use `cert_layoff_merged`** — it's stale (points at the old 174-record corpus
  build). Read the two sources directly.
- **Gold layer:** `cert_layoff_corpus/output/summaries/holdings.jsonl` (5,608 holdings back
  to 1979) + `taxonomy.json` (23-category frozen taxonomy). Used for facets, trend
  baselines, and the gold-holdings search collection.

### 4.2 Loader
Use **`cert_layoff_playground/corpuslib/corpus.py`** — it is schema-tolerant (handles the
v0.2/v0.4 mix) and **derives year from the OAH case-number prefix** when `decision_date` is
null (≈97 production records have null dates — corpuslib resolves them; do not rely on a
naive `decision_date[:4]`). v0.2.0 records simply lack a few newer fields
(`identity.scope`, `outcome.n_adjudicated_estimate`, `provenance.normalizations`) — tolerate
their absence; all load-bearing fields (holdings, issue.category, ruling.prevailing_party,
alj, district, year) are present in both versions.

### 4.3 Index build
Port **`cert_layoff_playground/prototypes/01-search-mcp/build_index.py`** + `engine.py`.
- Model: arctic-l-v2, `query:` prefix on queries only, RRF fusion (k=60), hybrid BM25 +
  embedding cosine. Validated: holdings hybrid R@10 ≈ 0.87, MRR ≈ 0.77.
- Collections: `holdings` (embedded), `gold_holdings` (embedded), `decisions` (full-text,
  BM25-only).
- `holding_text()` composes searchable text from `issue.statement` +
  `summary_style_holding` + `reasoning.summary`.
- **De-identify at index-build time** (already done in build_index.py via `corpuslib/deident.py`):
  respondent names never enter the index. Search/result layer is "District (ALJ)"-safe by
  construction.
- Pickle convention: keyed by content-hash of (ids + texts + model); atomic write; rebuild
  only on change.

### 4.4 Source-document conversion (new vs FPPC — FPPC was all PDF)
Many source decisions are **native RTF/DOC** (≈1,009 of ~1,552), not PDF. In the offline
build, convert every source doc to PDF for a consistent downloadable original:
`soffice --headless --convert-to pdf <file>` (LibreOffice handles RTF/DOC/DOCX robustly).
Upload PDFs to R2 under `docs/{year}/{oah_case_no}.pdf`.

The **in-app reader** renders the clean `full_text` from the record (nicer than a scan).
`full_text` contains respondent names — that is acceptable per the relaxed privacy stance.
Keep a name-scrub gate available (off by default) in case an external surface is ever wanted.

### 4.5 Build artifacts → R2
- `indexes/holdings.pkl`, `indexes/gold.pkl`, `indexes/decisions.pkl`
- A compact `metadata.json` (per-decision identity + per-holding facets) loaded into RAM at
  startup for fast filtering/aggregation without unpickling full objects.
- `docs/{year}/{case}.pdf`

---

## 5. Backend API

FastAPI, Python 3.12. Single service also serves the SPA static build (FPPC pattern).
All `/api/*` routes require a valid magic-link token (see §9).

### `GET /api/search`
Query params: `q` (string), `categories[]`, `year_start`, `year_end`, `district`, `alj`,
`prevailing_party` (district|respondent|mixed), `page`, `collection` (holdings|gold|decisions).

Response:
```json
{
  "total": 47,
  "page": 1,
  "insight": {
    "decision_count": 31,
    "year_range": [1999, 2025],
    "win_rate": { "district": 0.69, "respondent": 0.31, "baseline_district": 0.79 },
    "top_subtypes": [{"name": "certification mismatch", "count": 12}, ...],
    "top_aljs": [{"alj": "Wagner", "count": 8}, ...],
    "trend": [{"year": 2018, "district": 5, "respondent": 1}, ...]
  },
  "results": [
    {
      "holding_id": "...",
      "oah_case_no": "N2019...",
      "district": "Los Altos ESD",
      "alj": "Wagner",
      "year": 2019,
      "issue": {"category": "skipping", "subtype": "certification mismatch",
                "statement": "..."},
      "prevailing_party": "respondent",
      "remedies": ["retain_employee"],
      "summary_style_holding": "District's skipping of junior teachers failed because ...",
      "rank": 1
    }
  ]
}
```
- Over-fetch (top_k≈200), apply AND filters against the in-RAM metadata index, paginate
  (20/page) — exactly the FPPC router pattern.
- `insight` is computed over the **full filtered match set** (not just the page).
- **Do not expose raw relevance scores** to the client (FPPC convention) — rank only.

### `GET /api/decision/{oah_case_no}`
Returns full record for the reader: identity, board_action, outcome.overall,
all holdings (with arguments/facts/authorities/reasoning + quote anchors), `full_text`,
and the R2 PDF url for "download original."

### `GET /api/facets`
Returns available filter values + counts (categories from taxonomy, year range, top
districts, top ALJs) — drives the filter UI and the issue-explorer (v1.5).

### `POST /api/report`
Body: `{ categories[], year_start, year_end, district?, alj?, format: "html"|"pdf" }`.
Returns the deterministic report (see §7).

### `POST /api/events`
Append an analytics event (see §8). Fire-and-forget from the client.

---

## 6. Search & insight logic

- **Primary unit = the holding**, grouped by decision in the UI. Reuse the validated hybrid
  engine verbatim.
- **Insight strip** aggregations (new code, `backend/search/aggregate.py`):
  - `win_rate`: share of matched holdings where `ruling.prevailing_party` is district vs
    respondent. **Always show the corpus baseline** (~79% district) alongside, because the
    base rate is skewed — an elevated respondent win-rate is the signal, not the raw number.
  - `top_subtypes`, `top_aljs`: value counts over the match set.
  - `trend`: holdings per year split by prevailing party (sparkline).
- Compute insight from the in-RAM `metadata.json`, filtered to the match-set holding ids —
  cheap at this scale.

---

## 7. Report generator (deterministic, v1)

Reuse the annual-summary machinery: **`cert_layoff_corpus/pipeline/render_summary.py`** +
the runbook in **`cert_layoff_corpus/REPORTS.md`** (the annual report is already a
`GROUP BY summary_style_holding` in the house style).

- **Inputs:** issue category(ies), year range, optional district/ALJ.
- **Process:** filter holdings → group by category → render each `summary_style_holding`
  in the annual-volume house style ("... District (ALJ)").
- **Outputs:** HTML preview in-app + downloadable **PDF** (WeasyPrint: HTML → PDF).
  Optionally also docx (render_summary already produces docx) — PDF is the v1 priority.
- **Every line is anchored** to a real decision (link back to the in-app reader). No LLM.
- **v2 (deferred):** an optional, clearly-labeled Claude-API summary/commentary paragraph
  at the top; cover page; charts; saved/shareable report links.

---

## 8. Analytics (first-class priority)

One append-only `events` table serves **three goals at once**: product usage, a leakage-free
**eval relevance pool**, and **training data** (query→click positives, shown-not-clicked
negatives). This is the exact signal the FPPC fine-tuning effort lacked (see §12).

### Event schema (Postgres)
```sql
CREATE TABLE events (
  id           BIGSERIAL PRIMARY KEY,
  ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_token   TEXT,            -- magic-link token (who)
  session_id   TEXT,            -- client-generated per tab/session
  event_type   TEXT NOT NULL,   -- search | expand_holding | open_decision |
                                --   download_pdf | report | page_view
  query        TEXT,            -- raw query text (search events)
  query_type   TEXT,            -- nl | keyword (derived)
  filters      JSONB,           -- {categories, year_start, year_end, district, alj, ...}
  shown        JSONB,           -- [{holding_id, rank}, ...]  ← the relevance pool
  target_id    TEXT,            -- holding_id / oah_case_no acted on
  rank         INT,             -- rank of the acted-on result (for click models)
  dwell_ms     INT,             -- time on a decision/holding
  referrer     TEXT,            -- where the visit came from (share signal)
  user_agent   TEXT,
  ip_hash      TEXT             -- hashed; for share detection, not tracking
);
CREATE INDEX ON events (user_token, ts);
CREATE INDEX ON events (event_type, ts);
```

### What to log
- `search`: query, query_type, filters, **shown** (ranked holding ids) — the leakage-free pool.
- `expand_holding` / `open_decision` / `download_pdf`: target_id + rank → click positives;
  the unclicked entries in `shown` are trustworthy negatives.
- `report`: filters used.
- `page_view`: route + referrer (usage + sharing funnel).

### Why it matters
- **Product:** "is she using it / sharing it" — sessions per user_token, return visits,
  one token across many `ip_hash`/`referrer` = she forwarded the link.
- **Eval:** clicks form an unbiased relevance pool feeding `fppc-opinions-eval/src/scorer.py`
  (MRR/nDCG/P@k) — no lexical-discovery bias.
- **Training:** `(query → clicked holding)` positives + skip negatives, later.

Keep a tiny internal `/admin` (token-gated to you) showing recent searches + click-through,
or just query Postgres directly. Optionally add **PostHog** (free tier) for funnels/session
replay with near-zero effort — additive, not a replacement for the owned event log.

---

## 9. Auth — per-person magic links

- Each attorney gets a unique URL: `https://<app>/?k=<token>`.
- On first load the SPA stores the token (localStorage) and sends it on every `/api/*`
  call (header `X-Access-Token` or cookie).
- Backend middleware validates the token against a `users` table
  (`token, name, created_at, active`) — seedable from an env var for the prototype
  (`ACCESS_TOKENS=alice:Alice Smith,bob:Bob Jones`). Invalid/absent token → 401 + a simple
  "ask Nick for a link" page.
- The token is simultaneously: **auth**, **the analytics user id**, and the **share signal**.
- This is a low-sensitivity public-records corpus for a handful of firm attorneys — tokens
  are bearer links, not high-security auth. That's intentional and sufficient.

---

## 10. Frontend / UX

React 19 + Vite + Tailwind (FPPC stack). State in URL query params (bookmarkable/shareable).
Design: clean, warm-neutral, Inter for UI / serif for opinion body — professional, not flashy.

### Pages
- **`/` SearchPage** — query box (NL or keyword) + filters + **insight strip** + ranked
  **holding cards** (outcome chip green=district / amber=respondent, house-style paragraph,
  ALJ·district·year, expandable arguments/reasoning/authorities, "open decision →").
  Empty state = clickable issue-category pills (real categories from the taxonomy).
- **`/decision/:case` DecisionPage** — in-app reader (typeset `full_text`), header
  (case/district/ALJ/date/outcome), holdings list, **Download original PDF**.
- **`/reports` ReportsPage** — pick category(ies) + year range (+ district/ALJ) → preview →
  download PDF.
- **(v1.5)** `/alj/:name` ALJ profile (port `prototypes/03-alj-scouting`), `/issues` explorer.

### The results dashboard (target layout)
```
┌─ "skipping criteria special education" ──────────────[filters ▾]─┐
│  47 holdings · 31 decisions · 1999–2025                          │
│  ┌─ INSIGHT ─────────────────────────────────────────────────┐  │
│  │ District prevailed  ██████████████░░  69%  (baseline 79%)  │  │
│  │ Top sub-issues: certification mismatch · FTE math · ...    │  │
│  │ Most active ALJs: Wagner (8) · Cole (5) · Roman (4)        │  │
│  │ Trend ▁▂▂▅▃▂▆█  respondent wins rising since 2021          │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ ● RESPONDENT WON   Skipping · certification mismatch       │  │
│  │ Los Altos ESD (Wagner) · 2019 · OAH N2019…                │  │
│  │ "District's skipping of junior teachers failed because…"   │  │
│  │ ▸ arguments  ▸ reasoning  ▸ authorities   [open decision →]│  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```
All result interactions fire `/api/events`.

---

## 11. Tech stack, repo layout, deployment

### Stack
Backend: FastAPI, uvicorn, rank-bm25, sentence-transformers (arctic-l-v2), numpy,
SQLAlchemy/asyncpg (Postgres), httpx, weasyprint, pydantic-settings.
Frontend: React 19, Vite 7, React Router 7, Tailwind v4.
Offline build: corpuslib, sentence-transformers, LibreOffice (soffice), wrangler (R2 upload).

### Repo layout
```
cert_layoff_search_prototype/
  PLAN.md  CLAUDE.md  README.md
  backend/
    main.py config.py db.py auth.py models.py
    search/{engine.py, aggregate.py}
    reports/generate.py
    routers/{search.py, decisions.py, reports.py, events.py, facets.py}
    requirements.txt
  frontend/  (Vite app: src/pages, src/components, src/lib/api.js)
  build/     {build_index.py, convert_docs.py, upload_r2.py}
  Dockerfile  Procfile  nixpacks.toml  .env.example
```

### Deployment (Railway)
- `Dockerfile`: python:3.12-slim, install Node 20, `npm ci && npm run build` the frontend,
  copy backend, `uvicorn backend.main:app`.
- `Procfile`: `web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
- Railway Postgres add-on → `DATABASE_URL`.
- Startup (`main.py` lifespan): download `*.pkl` from R2 → load engine; run `events` table
  migration; load `metadata.json` into RAM.
- Env vars: `R2_INDEX_BASE_URL`, `R2_DOC_BASE_URL`, `DATABASE_URL`, `ACCESS_TOKENS`,
  `ENV=production`.
- R2: one public bucket, `indexes/` + `docs/` prefixes (mirror FPPC's `upload_pdfs.sh`).
- **Watch container RAM** for the 568M arctic model at cold start. If tight, swap to a
  bge-base/gte-modernbert-class model (matches OpenAI quality per our tuning report) and
  rebuild the index. Low-stakes — measure first.

---

## 12. Reusable code & hard-won lessons (read before coding)

### Port these (exact paths)
- `cert_layoff_playground/prototypes/01-search-mcp/engine.py` — hybrid BM25+embed RRF,
  pre-filtering, facets. ~150 lines, clean.
- `cert_layoff_playground/prototypes/01-search-mcp/build_index.py` — build-or-load pickle,
  MODELS registry, de-id at index time, holding_text composition.
- `cert_layoff_playground/corpuslib/{corpus.py, deident.py}` — schema-tolerant loader +
  de-id. Set `CORPUS_ROOT` to point at the chosen sources.
- `cert_layoff_corpus/pipeline/render_summary.py` + `REPORTS.md` — deterministic report core.
- `fppc-opinions-app/backend/` — overall app skeleton (routers, lifespan, R2 download,
  SPA serving, rate limiter). `fppc-opinions-eval/src/scorer.py` — the eval harness.

### Lessons (from cert_layoff coverage harness + FPPC tuning post-mortem)
- **Issue-spotting is solved; the corpus's value is grounding** (closed-book citation = 0%).
  → Lead with structured retrieval + analytics, not generation.
- **Outcome data skews ~79% district-win.** → Always present win-rate per-issue against the
  baseline; never a bare percentage.
- **Naive RAG buys grounding but not usefulness/correctness, and is net-negative on outcome
  prediction.** → No generative answers in v1.
- **Click data is the unbiased eval/training signal the FPPC tuning effort lacked.** → Log
  `shown` + clicks from day one (§8).
- **Fine-tuning gave only marginal, fragile gains; open models already match OpenAI.** →
  Don't fine-tune yet; CPU arctic-l-v2 is plenty.
- **De-id covers roster names only** — non-roster names can appear in `full_text`. Fine for
  this relaxed-privacy use; keep the name-scrub gate available if an external surface arises.
- Schema is mixed v0.2/v0.4 across the slice — rely on `corpuslib` tolerance, not raw field
  access.

---

## 13. Build phases

1. **Scaffold** repo (backend FastAPI + frontend Vite/React/Tailwind + Dockerfile/Procfile).
2. **Offline build pipeline** (`build/`): load slice via corpuslib → de-id → build indexes →
   convert source docs to PDF → `metadata.json` → upload to R2.
3. **Search API + holding cards + facets** (port engine; wire `/api/search`, `/api/facets`).
4. **Insight strip** (`aggregate.py` + frontend INSIGHT panel).
5. **Decision reader + download original** (`/api/decision`, DecisionPage).
6. **Report generator** (`reports/generate.py`, `/api/report`, ReportsPage, PDF via WeasyPrint).
7. **Auth (magic links) + analytics** (`auth.py`, Postgres `events`, `/api/events`, client hooks).
8. **Deploy to Railway**, smoke-test end-to-end, seed Alice's token, send the link.
9. **(v1.5)** ALJ profiles + issue explorer. **(v2)** LLM report summary + report enhancements.

---

## 14. Open items to confirm during the build
- Final embedding model after RAM measurement on Railway (arctic-l-v2 vs smaller).
- Whether to include lab 2004/2009 (default: yes, ~666 decisions) or stay v0.4.0-only (412).
- Report output formats beyond PDF (docx? saved links?) — PDF only for v1.
- PostHog yes/no (default: skip for v1; owned Postgres log is the requirement).
