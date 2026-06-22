import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getFacets, track } from '../lib/api'

/*
 * ALJ Profiles landing (route "/alj"). A searchable picker over every ALJ in the
 * corpus; choosing one routes to /alj/{name} (the existing scouting profile).
 * This is the easy entry point — previously profiles were only reachable by
 * clicking an ALJ name in search results.
 */
export default function AljIndexPage() {
  const navigate = useNavigate()
  const [aljs, setAljs] = useState(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    const c = new AbortController()
    getFacets(c.signal)
      .then((f) => setAljs(f?.aljs || []))
      .catch(() => setAljs([]))
    track('page_view', { target_id: '/alj' })
    return () => c.abort()
  }, [])

  const sorted = useMemo(
    () => [...(aljs || [])].filter((a) => a && a.name).sort((a, b) => (b.count || 0) - (a.count || 0)),
    [aljs],
  )

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return sorted
    return sorted.filter((a) => a.name.toLowerCase().includes(needle))
  }, [sorted, q])

  function open(name) {
    navigate(`/alj/${encodeURIComponent(name)}`)
  }

  return (
    <div className="max-w-3xl mx-auto">
      <header className="mb-6">
        <span className="eyebrow">Scouting profiles</span>
        <h1 className="text-2xl font-semibold text-text-heading leading-tight mt-1 mb-2">
          ALJ profiles
        </h1>
        <p className="text-text-secondary text-sm leading-relaxed max-w-xl">
          Pick a judge to see how they rule — win-rate vs. the corpus baseline, a breakdown by
          issue, and representative holdings. {sorted.length || ''} administrative law judges have
          decided layoff matters in the corpus.
        </p>
      </header>

      {/* Picker */}
      <div className="relative mb-4">
        <svg
          className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted"
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M21 21l-4.35-4.35M11 18a7 7 0 100-14 7 7 0 000 14z" />
        </svg>
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Select or filter by judge name…"
          className="w-full rounded-xl border border-border bg-surface pl-10 pr-3 py-2.5 text-sm outline-none focus:border-accent card-shadow"
          aria-label="Filter ALJs by name"
        />
      </div>

      {aljs == null ? (
        <ListSkeleton />
      ) : filtered.length === 0 ? (
        <p className="text-sm text-text-muted px-1 py-8 text-center">No judge matches “{q}”.</p>
      ) : (
        <>
          <div className="text-xs text-text-muted mb-2 px-1 tabular-nums">
            {filtered.length} {filtered.length === 1 ? 'judge' : 'judges'}
            {q ? '' : ' · most active first'}
          </div>
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {filtered.map((a) => (
              <li key={a.name}>
                <button
                  onClick={() => open(a.name)}
                  className="w-full flex items-center gap-3 rounded-lg border border-border bg-surface px-3.5 py-2.5 text-left card-shadow card-shadow-hover transition-shadow hover:border-accent group"
                >
                  <span className="text-sm font-medium text-text-primary group-hover:text-accent transition-colors truncate">
                    {a.name}
                  </span>
                  {a.count != null && (
                    <span className="ml-auto shrink-0 text-xs text-text-muted tabular-nums">
                      {a.count} decision{a.count === 1 ? '' : 's'}
                    </span>
                  )}
                  <svg className="shrink-0 w-4 h-4 text-text-muted group-hover:text-accent transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function ListSkeleton() {
  return (
    <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2" aria-hidden="true">
      {Array.from({ length: 10 }).map((_, i) => (
        <li key={i} className="h-11 rounded-lg border border-border bg-surface animate-pulse" />
      ))}
    </ul>
  )
}
