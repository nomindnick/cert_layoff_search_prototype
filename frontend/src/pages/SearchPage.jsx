import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import SearchBar from '../components/SearchBar'
import FilterBar from '../components/FilterBar'
import InsightStrip from '../components/InsightStrip'
import HoldingCard from '../components/HoldingCard'
import { search as apiSearch, getFacets, track } from '../lib/api'
import { titleize } from '../lib/format'

const PAGE_SIZE = 20

/*
 * The dashboard (PLAN.md §10). Search state lives entirely in the URL so every
 * view is bookmarkable/shareable. On any change we refetch /api/search, render
 * the InsightStrip over the full match set, and the page of HoldingCards.
 */
export default function SearchPage() {
  const [params, setParams] = useSearchParams()

  // ── URL-derived state ──
  const q = params.get('q') || ''
  const page = parseInt(params.get('page') || '1', 10)
  const categories = (params.get('categories') || '').split(',').filter(Boolean)
  const yearStart = params.get('year_start') ? parseInt(params.get('year_start'), 10) : null
  const yearEnd = params.get('year_end') ? parseInt(params.get('year_end'), 10) : null
  const district = params.get('district') || null
  const alj = params.get('alj') || null
  const prevailingParty = params.get('prevailing_party') || null

  const hasQueryOrFilter =
    !!q || categories.length > 0 || !!yearStart || !!yearEnd || !!district || !!alj || !!prevailingParty

  // ── Data state ──
  const [facets, setFacets] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [retry, setRetry] = useState(0)
  const abortRef = useRef(null)

  // Load facets once.
  useEffect(() => {
    const c = new AbortController()
    getFacets(c.signal)
      .then(setFacets)
      .catch(() => {})
    return () => c.abort()
  }, [])

  // Run search whenever query/filters/page change.
  useEffect(() => {
    if (!hasQueryOrFilter) {
      setData(null)
      setError(null)
      return
    }
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)

    apiSearch(
      { q, categories, year_start: yearStart, year_end: yearEnd, district, alj, prevailing_party: prevailingParty, page },
      controller.signal,
    )
      .then((res) => {
        setData(res)
        setLoading(false)
        // Log the search with the ranked shown ids (the leakage-free relevance pool).
        const shown = (res.results || []).map((r) => ({ holding_id: r.holding_id, rank: r.rank }))
        track('search', {
          query: q || null,
          query_type: classifyQuery(q),
          filters: { categories, year_start: yearStart, year_end: yearEnd, district, alj, prevailing_party: prevailingParty },
          shown,
        })
      })
      .catch((err) => {
        if (err.name === 'AbortError' || err.status === 401) return
        setError(err.status === 404 ? 'error' : 'network')
        setLoading(false)
      })

    window.scrollTo({ top: 0, behavior: 'smooth' })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, page, categories.join(','), yearStart, yearEnd, district, alj, prevailingParty, retry])

  // ── URL writers ──
  function update(overrides, { resetPage = true } = {}) {
    const next = new URLSearchParams()
    const merged = {
      q,
      categories,
      year_start: yearStart,
      year_end: yearEnd,
      district,
      alj,
      prevailing_party: prevailingParty,
      page: resetPage ? 1 : page,
      ...overrides,
    }
    if (merged.q) next.set('q', merged.q)
    if (merged.categories?.length) next.set('categories', merged.categories.join(','))
    if (merged.year_start) next.set('year_start', String(merged.year_start))
    if (merged.year_end) next.set('year_end', String(merged.year_end))
    if (merged.district) next.set('district', merged.district)
    if (merged.alj) next.set('alj', merged.alj)
    if (merged.prevailing_party) next.set('prevailing_party', merged.prevailing_party)
    if (merged.page && merged.page > 1) next.set('page', String(merged.page))
    setParams(next)
  }

  const total = data?.total ?? 0
  const results = data?.results ?? []
  const insight = data?.insight ?? null
  const pageSize = data?.page_size ?? PAGE_SIZE
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div>
      <h1 className="sr-only">Search certificated-layoff holdings</h1>

      <div className="mb-6">
        <SearchBar value={q} onSearch={(val) => update({ q: val })} />
      </div>

      {facets && hasQueryOrFilter && (
        <div className="mb-6">
          <FilterBar
            facets={facets}
            categories={categories}
            yearStart={yearStart}
            yearEnd={yearEnd}
            district={district}
            alj={alj}
            prevailingParty={prevailingParty}
            onCategoriesChange={(c) => update({ categories: c })}
            onYearChange={({ start, end }) => update({ year_start: start, year_end: end })}
            onDistrictChange={(d) => update({ district: d })}
            onAljChange={(a) => update({ alj: a })}
            onPrevailingPartyChange={(p) => update({ prevailing_party: p })}
            onClearAll={() =>
              update({
                categories: [],
                year_start: null,
                year_end: null,
                district: null,
                alj: null,
                prevailing_party: null,
              })
            }
          />
        </div>
      )}

      {!hasQueryOrFilter ? (
        <EmptyState facets={facets} onPick={(key) => update({ categories: [key] })} onSearch={(val) => update({ q: val })} />
      ) : error ? (
        <ErrorState kind={error} onRetry={() => setRetry((r) => r + 1)} />
      ) : (
        <div className={loading && data ? 'results-loading' : 'results-ready'}>
          {/* Result count line */}
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 mb-4 text-sm text-text-secondary">
            {loading && !data ? (
              <span className="text-text-muted">Searching…</span>
            ) : (
              <>
                <span className="font-medium text-text-primary tabular-nums">{total}</span>
                <span>holding{total === 1 ? '' : 's'}</span>
                {insight?.decision_count != null && (
                  <>
                    <span className="text-text-muted">·</span>
                    <span className="tabular-nums">{insight.decision_count}</span>
                    <span>decision{insight.decision_count === 1 ? '' : 's'}</span>
                  </>
                )}
                {insight?.year_range && (
                  <>
                    <span className="text-text-muted">·</span>
                    <span className="tabular-nums">
                      {insight.year_range[0]}
                      {insight.year_range[1] !== insight.year_range[0] ? `–${insight.year_range[1]}` : ''}
                    </span>
                  </>
                )}
              </>
            )}
          </div>

          {insight && total > 0 && (
            <div className="mb-6">
              <InsightStrip insight={insight} />
            </div>
          )}

          {loading && !data ? (
            <SkeletonList />
          ) : results.length === 0 ? (
            <NoResults />
          ) : (
            <div className="flex flex-col gap-4">
              {results.map((hit) => (
                <HoldingCard key={hit.holding_id} hit={hit} />
              ))}
            </div>
          )}

          {totalPages > 1 && results.length > 0 && (
            <Pagination
              page={page}
              totalPages={totalPages}
              total={total}
              pageSize={pageSize}
              onChange={(p) => update({ page: p }, { resetPage: false })}
            />
          )}
        </div>
      )}
    </div>
  )
}

/* ── Empty / landing state: clickable category pills ─────────── */
function EmptyState({ facets, onPick, onSearch }) {
  const cats = facets?.categories || []
  const examples = [
    'skipping for special education credential',
    'seniority tie-breaker criteria',
    'FTE reduction math error',
    'particular kinds of services bumping rights',
  ]
  return (
    <div className="max-w-3xl mx-auto text-center py-10 md:py-16 animate-fade-in">
      <h2 className="text-2xl md:text-[1.7rem] font-semibold text-text-heading mb-3 leading-tight">
        The shape of the law on teacher-layoff holdings
      </h2>
      <p className="text-text-secondary mb-8 max-w-xl mx-auto leading-relaxed">
        Search ~679 California OAH decisions by the contested issue an ALJ resolved. See who
        prevails, on what, before which judge, and which way the trend is moving — every claim
        traceable to a real decision.
      </p>

      {cats.length > 0 && (
        <div className="mb-10">
          <span className="eyebrow block mb-3">Browse by issue</span>
          <div className="flex flex-wrap justify-center gap-2">
            {cats.map((c) => (
              <button
                key={c.key}
                onClick={() => onPick(c.key)}
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3.5 py-1.5 text-sm text-text-primary hover:border-accent hover:text-accent transition-colors card-shadow"
              >
                {c.label || titleize(c.key)}
                {c.count != null && <span className="text-xs text-text-muted">{c.count}</span>}
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <span className="eyebrow block mb-3">Or try a question</span>
        <div className="flex flex-col items-center gap-2">
          {examples.map((ex) => (
            <button
              key={ex}
              onClick={() => onSearch(ex)}
              className="text-sm text-accent hover:text-accent-hover hover:underline underline-offset-2"
            >
              “{ex}”
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── States ──────────────────────────────────────────────────── */
function ErrorState({ kind, onRetry }) {
  return (
    <div className="text-center py-16 animate-fade-in">
      <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-border-light mb-5">
        <svg className="w-6 h-6 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-text-primary mb-2">
        {kind === 'network' ? 'Search engine is warming up' : 'Something went wrong'}
      </h2>
      <p className="text-text-secondary text-sm mb-6 max-w-md mx-auto">
        {kind === 'network'
          ? 'The service may be starting up. This usually takes a moment — please try again shortly.'
          : 'An unexpected error occurred while searching. Please try again.'}
      </p>
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-accent border border-accent rounded-lg hover:bg-accent-light transition-colors"
      >
        Retry search
      </button>
    </div>
  )
}

function NoResults() {
  return (
    <div className="text-center py-16 animate-fade-in">
      <h2 className="text-lg font-semibold text-text-primary mb-2">No holdings match</h2>
      <p className="text-text-secondary text-sm max-w-md mx-auto">
        Try broadening the issue category, widening the year range, or removing a district / ALJ filter.
      </p>
    </div>
  )
}

function SkeletonList() {
  return (
    <div className="flex flex-col gap-4" aria-hidden="true">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="rounded-xl border border-border bg-surface p-5 card-shadow">
          <div className="h-5 w-40 bg-border-light rounded mb-3 animate-pulse" />
          <div className="h-3 w-56 bg-border-light rounded mb-4 animate-pulse" />
          <div className="h-3 w-full bg-border-light rounded mb-2 animate-pulse" />
          <div className="h-3 w-11/12 bg-border-light rounded mb-2 animate-pulse" />
          <div className="h-3 w-3/4 bg-border-light rounded animate-pulse" />
        </div>
      ))}
    </div>
  )
}

function Pagination({ page, totalPages, total, pageSize, onChange }) {
  const from = (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <nav className="flex items-center justify-between mt-8 pt-2" aria-label="Pagination">
      <span className="text-sm text-text-muted tabular-nums">
        {from}–{to} of {total}
      </span>
      <div className="flex items-center gap-2">
        <PageBtn disabled={page <= 1} onClick={() => onChange(page - 1)}>
          Previous
        </PageBtn>
        <span className="text-sm text-text-secondary tabular-nums px-1">
          Page {page} of {totalPages}
        </span>
        <PageBtn disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
          Next
        </PageBtn>
      </div>
    </nav>
  )
}

function PageBtn({ disabled, onClick, children }) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className="px-3 py-1.5 text-sm font-medium rounded-lg border border-border text-text-primary hover:border-accent hover:text-accent disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-border disabled:hover:text-text-primary transition-colors"
    >
      {children}
    </button>
  )
}

/* Heuristic query type for analytics: a multi-word phrase reads as NL. */
function classifyQuery(q) {
  if (!q) return null
  const words = q.trim().split(/\s+/)
  return words.length >= 4 ? 'nl' : 'keyword'
}
