# Cert Layoff Search — Frontend

React 19 + Vite 7 + React Router 7 + Tailwind v4 SPA for the cert-layoff search
& insight app. See the root `PLAN.md` (§10) and `CLAUDE.md` for product intent.

## Develop

```bash
npm install          # (node may be absent in the build env — install on your machine)
npm run dev          # Vite dev server; proxies /api -> http://localhost:8000
```

Open `http://localhost:5173/?k=demo` — the `?k=` token is read once, persisted to
localStorage, and sent as `X-Access-Token` on every API call. A `demo` token works
out of the box when the backend runs in development.

## Build

```bash
npm run build        # emits to ./dist (served by the FastAPI backend)
```

## Layout

```
src/
  main.jsx            entry (BrowserRouter)
  App.jsx             routes
  index.css           Tailwind import + design tokens (Inter UI / serif body)
  lib/
    api.js            token + session + track(); search/getDecision/getFacets/runReport/getMe
    format.js         pure formatting helpers (titleize, outcomeMeta, …)
  components/
    Layout.jsx        header/nav/footer; bootstraps token, confirms via /api/me, page_view
    SearchBar.jsx     NL / keyword query box
    FilterBar.jsx     category multi-select, year range, district, ALJ, prevailing party
    InsightStrip.jsx  win-rate bar + baseline marker, top sub-issues, top ALJs, SVG sparkline
    HoldingCard.jsx   outcome chip + house-style paragraph + expandable detail
    DecisionReader.jsx full record: header, board action, holdings, full_text, download PDF
  pages/
    SearchPage.jsx    the dashboard; URL-driven search state
    DecisionPage.jsx  in-app reader route (tracks dwell)
    ReportsPage.jsx   deterministic report builder + PDF download
    NoAccess.jsx      access gate (shown on 401)
```

## Conventions

- **Search state lives in the URL** (`?q=&categories=a,b&year_start=…&page=`) so
  every view is bookmarkable and shareable.
- **Analytics fire from the client** via `track()`: `search` (with the ranked
  `shown` holding ids), `expand_holding`, `open_decision`, `download_pdf`,
  `report`, `page_view`.
- **No raw scores** are shown — rank only, per the API contract.
- Only fields defined in the backend API contract are used; everything tolerates
  missing keys.
