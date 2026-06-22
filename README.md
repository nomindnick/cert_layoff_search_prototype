# Cert Layoff Search

A search + insight web app over ~679 California OAH certificated (teacher) layoff proposed
decisions. The atomic unit is the **holding** — one contested issue an ALJ resolved. The UI
surfaces structured signal (who wins, on what issue, before which ALJ, trending which way),
with every claim traceable to a real decision. It is **not** a chatbot.

Audience: a few firm L&E attorneys. See **`PLAN.md`** (authoritative build guide) and
**`CLAUDE.md`** (conventions) for the full intent.

## Architecture (one line)

Offline build → indexes + records + metadata on Cloudflare R2 → one FastAPI service on
Railway that pulls those artifacts at startup, serves the API, and serves the built React
SPA. Search is BM25 over a tiny corpus in v1 (hybrid embeddings are opt-in).

```
backend/   FastAPI (API + serves the built SPA)
frontend/  Vite + React 19 + Tailwind v4
build/     offline: build_index.py, convert_docs.py, upload_r2.py (run on the desktop)
build/output/  generated artifacts (gitignored): indexes/*.pkl, records.json, metadata.json
```

## Local development

You need the offline build artifacts before the backend has anything to serve. Either run
the offline build locally, or point the backend at R2 (set `R2_INDEX_BASE_URL`).

1. **Configure env**

   ```bash
   cp .env.example .env
   # edit as needed; defaults are fine for local dev
   ```

2. **Offline build** (produces `build/output/indexes/*.pkl`, `records.json`, `metadata.json`)

   ```bash
   python build/build_index.py          # BM25-only (v1 default; no torch)
   # python build/build_index.py --embed  # also build arctic embeddings (heavy deps)
   ```

   Heavy embedding deps (only for `--embed`) live in `build/requirements-embed.txt`.

3. **Backend** (BM25-only by default; boots without torch)

   ```bash
   pip install -r requirements.txt
   uvicorn backend.main:app --reload     # http://localhost:8000
   ```

4. **Frontend** (Vite dev server, proxies `/api` → `localhost:8000`)

   ```bash
   cd frontend && npm install && npm run dev
   ```

   Open the dev URL with a token: `http://localhost:5173/?k=demo`.

To serve the production bundle locally instead, run `./build.sh` then just the backend —
FastAPI serves `frontend/dist` at `/`.

## Deployment (Railway)

- Builds from the **`Dockerfile`** (python:3.12-slim + Node 20: builds the SPA, installs
  BM25-only deps, runs uvicorn). `Procfile` / `nixpacks.toml` are alternative build paths.
- Add the **Railway Postgres** plugin → it injects `DATABASE_URL` for the events log.
- Set `R2_INDEX_BASE_URL` + `R2_DOC_BASE_URL` so the service pulls indexes/records/metadata
  from R2 at startup (the Railway filesystem is ephemeral; nothing is baked into the image).
- Set `ACCESS_TOKENS` (one per attorney) and `ENV=production`.
- PDFs render via **xhtml2pdf** (pure Python, no system libraries).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ENV` | `development` | `development` enables permissive CORS + the `demo` token |
| `INDEX_DIR` | `build/output/indexes` | Local dir for the `*.pkl` indexes |
| `RECORDS_PATH` | `build/output/records.json` | Local served-records file |
| `METADATA_PATH` | `build/output/metadata.json` | Local facets/stats file |
| `R2_INDEX_BASE_URL` | `""` | R2 base for indexes/records/metadata (download at startup if local missing) |
| `R2_DOC_BASE_URL` | `""` | R2 base for source PDFs (`docs/{year}/{stem}.pdf`) |
| `DATABASE_URL` | `sqlite:///./events.db` | Events DB (sqlite local, postgres on Railway) |
| `ACCESS_TOKENS` | `demo:Demo User` | Magic-link tokens, `tok:Name,tok2:Name2` |
| `EMBED_BACKEND` | `none` | `none` (BM25-only) / `arctic` / `openai` (hybrid; needs embedded indexes) |
| `OPENAI_API_KEY` | `""` | Only when `EMBED_BACKEND=openai` |

## Notes

- v1 serves **BM25-only** so the image needs no torch and boots fast/cheap. Hybrid search is
  enabled later by building embedded indexes and setting `EMBED_BACKEND`.
- All served text is **de-identified at build time** (roster names dropped); original PDFs on
  R2 retain names (acceptable per the relaxed-privacy stance for this public-records corpus).
- Never commit indexes, records, metadata, `.env`, or `events.db` — they are gitignored.
