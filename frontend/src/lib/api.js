/*
 * API client for the Cert Layoff Search backend.
 *
 * Responsibilities (per the build contract, section FRONTEND / src/lib/api.js):
 *   1. Read the access token from the URL (?k=), persist it to localStorage,
 *      and send it as header X-Access-Token on every /api call.
 *   2. On a 401 response, route the browser to the NoAccess page.
 *   3. Expose typed-ish helpers: search, getDecision, getFacets, runReport, getMe.
 *   4. Provide track(event_type, payload) that POSTs to /api/events with a
 *      localStorage-persisted session_id (crypto.randomUUID), fire-and-forget.
 *
 * Everything is plain fetch — no extra dependencies.
 */

const TOKEN_KEY = 'clx_token'
const SESSION_KEY = 'clx_session_id'

// ── Token management ─────────────────────────────────────────
// Read ?k= from the URL once, persist, and strip it so it doesn't linger in
// the address bar / get copied into shared links accidentally.
export function bootstrapToken() {
  try {
    const url = new URL(window.location.href)
    const k = url.searchParams.get('k')
    if (k) {
      localStorage.setItem(TOKEN_KEY, k)
      url.searchParams.delete('k')
      const clean = url.pathname + (url.searchParams.toString() ? '?' + url.searchParams.toString() : '') + url.hash
      window.history.replaceState({}, '', clean)
    }
  } catch {
    /* non-browser / malformed URL — ignore */
  }
  return getToken()
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore */
  }
}

// ── Session id (per browser, persisted) ──────────────────────
export function getSessionId() {
  try {
    let sid = localStorage.getItem(SESSION_KEY)
    if (!sid) {
      sid =
        typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : 'sid-' + Math.random().toString(36).slice(2) + Date.now().toString(36)
      localStorage.setItem(SESSION_KEY, sid)
    }
    return sid
  } catch {
    return 'sid-ephemeral'
  }
}

// ── Core request helper ──────────────────────────────────────
function headers(extra = {}) {
  const h = { 'X-Access-Token': getToken(), ...extra }
  return h
}

function goNoAccess() {
  if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/no-access')) {
    window.location.assign('/no-access')
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const opts = { method, headers: headers(), signal }
  if (body !== undefined) {
    opts.headers = headers({ 'Content-Type': 'application/json' })
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(path, opts)
  if (res.status === 401) {
    goNoAccess()
    const err = new Error('unauthorized')
    err.status = 401
    throw err
  }
  if (!res.ok) {
    const err = new Error(`request failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return res
}

async function getJSON(path, signal) {
  const res = await request(path, { signal })
  return res.json()
}

// ── Query-string helper ──────────────────────────────────────
function qs(params) {
  const sp = new URLSearchParams()
  for (const [key, val] of Object.entries(params)) {
    if (val == null || val === '') continue
    if (Array.isArray(val)) {
      const joined = val.filter(Boolean).join(',')
      if (joined) sp.set(key, joined)
    } else {
      sp.set(key, String(val))
    }
  }
  return sp.toString()
}

// ── Public API ───────────────────────────────────────────────

export function getMe(signal) {
  return getJSON('/api/me', signal)
}

export function getFacets(signal) {
  return getJSON('/api/facets', signal)
}

/**
 * Search holdings.
 * @param {object} params - { q, categories[], year_start, year_end, district,
 *                            alj, prevailing_party, collection, page }
 */
export function search(params, signal) {
  const query = qs({
    q: params.q,
    categories: params.categories,
    year_start: params.year_start,
    year_end: params.year_end,
    district: params.district,
    alj: params.alj,
    prevailing_party: params.prevailing_party,
    collection: params.collection || 'holdings',
    page: params.page || 1,
  })
  return getJSON(`/api/search?${query}`, signal)
}

export function getDecision(caseNo, signal) {
  return getJSON(`/api/decision/${encodeURIComponent(caseNo)}`, signal)
}

export function getHolding(holdingId, signal) {
  return getJSON(`/api/holding/${encodeURIComponent(holdingId)}`, signal)
}

export function getAlj(name, signal) {
  return getJSON(`/api/alj/${encodeURIComponent(name)}`, signal)
}

/**
 * Run a deterministic report.
 * @param {object} params - { categories[], year_start, year_end, district?, alj?, format }
 * For format "html" returns parsed JSON { html, n_holdings, title }.
 * For format "pdf" returns a Blob (caller saves it).
 */
export async function runReport(params, signal) {
  const res = await request('/api/report', { method: 'POST', body: params, signal })
  if (params.format === 'pdf') return res.blob()
  return res.json()
}

/**
 * Fire-and-forget analytics. Never throws.
 * @param {string} eventType
 * @param {object} payload - { query?, query_type?, filters?, shown?, target_id?, rank?, dwell_ms?, referrer? }
 */
export function track(eventType, payload = {}) {
  try {
    const body = JSON.stringify({
      event_type: eventType,
      session_id: getSessionId(),
      referrer: payload.referrer ?? document.referrer ?? null,
      ...payload,
    })
    // keepalive lets the request survive a navigation (open_decision, etc.).
    // We use fetch rather than sendBeacon because sendBeacon can't attach the
    // X-Access-Token header the API requires.
    fetch('/api/events', {
      method: 'POST',
      headers: headers({ 'Content-Type': 'application/json' }),
      body,
      keepalive: true,
    }).catch(() => {})
  } catch {
    /* analytics must never break the app */
  }
}
