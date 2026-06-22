import { useEffect, useState } from 'react'
import { getFacets, runReport, track } from '../lib/api'
import { titleize } from '../lib/format'

/*
 * Deterministic report generator (PLAN.md §7). Pick issue category(ies) + year
 * range (+ optional district/ALJ), preview the HTML in-app, then download a PDF.
 * No LLM — every line is a real holding rendered in the annual-volume house style.
 */
export default function ReportsPage() {
  const [facets, setFacets] = useState(null)
  const [categories, setCategories] = useState([])
  const [yearStart, setYearStart] = useState('')
  const [yearEnd, setYearEnd] = useState('')
  const [district, setDistrict] = useState('')
  const [alj, setAlj] = useState('')

  const [preview, setPreview] = useState(null) // { html, n_holdings, title }
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const c = new AbortController()
    getFacets(c.signal).then(setFacets).catch(() => {})
    // Default the year range to the full corpus once facets arrive.
    return () => c.abort()
  }, [])

  useEffect(() => {
    if (facets && yearStart === '' && yearEnd === '') {
      if (facets.year_min != null) setYearStart(String(facets.year_min))
      if (facets.year_max != null) setYearEnd(String(facets.year_max))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facets])

  const catOptions = facets?.categories || []
  const canRun = categories.length > 0

  function toggleCat(key) {
    setCategories((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]))
  }

  function buildParams(format) {
    return {
      categories,
      year_start: yearStart ? parseInt(yearStart, 10) : null,
      year_end: yearEnd ? parseInt(yearEnd, 10) : null,
      district: district.trim() || null,
      alj: alj.trim() || null,
      format,
    }
  }

  async function onPreview() {
    if (!canRun) return
    setLoading(true)
    setError(null)
    try {
      const res = await runReport(buildParams('html'))
      setPreview(res)
      track('report', {
        filters: { categories, year_start: yearStart || null, year_end: yearEnd || null, district: district || null, alj: alj || null },
      })
    } catch (err) {
      if (err.status !== 401) setError('Could not generate the report. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  async function onDownload() {
    if (!canRun) return
    setDownloading(true)
    setError(null)
    try {
      const blob = await runReport(buildParams('pdf'))
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = reportFilename(categories, yearStart, yearEnd)
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      track('download_pdf', {
        target_id: 'report',
        filters: { categories, year_start: yearStart || null, year_end: yearEnd || null, district: district || null, alj: alj || null },
      })
    } catch (err) {
      if (err.status === 501) setError('PDF export is not available in this environment.')
      else if (err.status !== 401) setError('Could not download the PDF. Please try again.')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
      {/* ── Controls ─────────────────────────────────────────── */}
      <aside className="lg:col-span-4 xl:col-span-3">
        <h1 className="text-xl font-semibold text-text-heading mb-1">Reports</h1>
        <p className="text-sm text-text-secondary mb-6 leading-relaxed">
          Build a deterministic summary in the firm’s annual-volume house style. Every line is
          a real holding — no generated text.
        </p>

        <div className="rounded-xl border border-border bg-surface card-shadow p-4 flex flex-col gap-5">
          <div>
            <span className="filter-label">Issue categories</span>
            <div className="flex flex-col gap-1 max-h-72 overflow-auto pr-1">
              {catOptions.length === 0 && <span className="text-sm text-text-muted">Loading…</span>}
              {catOptions.map((c) => (
                <label
                  key={c.key}
                  className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-surface-soft cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={categories.includes(c.key)}
                    onChange={() => toggleCat(c.key)}
                    className="accent-[var(--color-accent)] w-4 h-4"
                  />
                  <span className="flex-1 text-sm text-text-primary">{c.label || titleize(c.key)}</span>
                  {c.count != null && <span className="text-xs text-text-muted tabular-nums">{c.count}</span>}
                </label>
              ))}
            </div>
          </div>

          <div>
            <span className="filter-label">Year range</span>
            <div className="flex items-center gap-2">
              <input
                type="number"
                inputMode="numeric"
                value={yearStart}
                onChange={(e) => setYearStart(e.target.value)}
                placeholder={facets?.year_min != null ? String(facets.year_min) : 'From'}
                className="w-full rounded-lg border border-border bg-surface px-2.5 py-2 text-sm tabular-nums outline-none focus:border-accent"
                aria-label="Year from"
              />
              <span className="text-text-muted">–</span>
              <input
                type="number"
                inputMode="numeric"
                value={yearEnd}
                onChange={(e) => setYearEnd(e.target.value)}
                placeholder={facets?.year_max != null ? String(facets.year_max) : 'To'}
                className="w-full rounded-lg border border-border bg-surface px-2.5 py-2 text-sm tabular-nums outline-none focus:border-accent"
                aria-label="Year to"
              />
            </div>
          </div>

          <div>
            <span className="filter-label">District (optional)</span>
            <input
              value={district}
              onChange={(e) => setDistrict(e.target.value)}
              placeholder="Any district"
              list="report-districts"
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <datalist id="report-districts">
              {(facets?.districts || []).slice(0, 200).map((d) => (
                <option key={d.name} value={d.name} />
              ))}
            </datalist>
          </div>

          <div>
            <span className="filter-label">ALJ (optional)</span>
            <input
              value={alj}
              onChange={(e) => setAlj(e.target.value)}
              placeholder="Any ALJ"
              list="report-aljs"
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <datalist id="report-aljs">
              {(facets?.aljs || []).slice(0, 200).map((a) => (
                <option key={a.name} value={a.name} />
              ))}
            </datalist>
          </div>

          <div className="flex flex-col gap-2 pt-1">
            <button
              onClick={onPreview}
              disabled={!canRun || loading}
              className="w-full px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Generating…' : 'Preview report'}
            </button>
            <button
              onClick={onDownload}
              disabled={!canRun || downloading}
              className="w-full px-4 py-2.5 rounded-lg border border-accent text-accent text-sm font-medium hover:bg-accent-light disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {downloading ? 'Preparing PDF…' : 'Download PDF'}
            </button>
            {!canRun && (
              <p className="text-xs text-text-muted text-center">Select at least one issue category.</p>
            )}
            {error && <p className="text-xs text-[var(--color-win-respondent)] text-center">{error}</p>}
          </div>
        </div>
      </aside>

      {/* ── Preview ──────────────────────────────────────────── */}
      <section className="lg:col-span-8 xl:col-span-9">
        {!preview ? (
          <div className="h-full min-h-[24rem] rounded-xl border border-dashed border-border flex items-center justify-center text-center p-10">
            <div>
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-surface-soft border border-border-light mb-4">
                <svg className="w-6 h-6 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.4} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p className="text-sm text-text-secondary max-w-sm">
                Choose one or more issue categories and a year range, then preview the report here.
              </p>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-border bg-surface card-shadow overflow-hidden">
            <div className="flex flex-wrap items-center gap-3 border-b border-border-light px-5 py-3.5">
              <div>
                <h2 className="text-sm font-semibold text-text-heading">{preview.title || 'Report'}</h2>
                <span className="text-xs text-text-muted tabular-nums">
                  {preview.n_holdings ?? 0} holding{preview.n_holdings === 1 ? '' : 's'}
                </span>
              </div>
              <button
                onClick={onDownload}
                disabled={downloading}
                className="ml-auto inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-accent text-accent text-sm font-medium hover:bg-accent-light disabled:opacity-40 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M12 4v12m0 0l-4-4m4 4l4-4M4 20h16" />
                </svg>
                {downloading ? 'Preparing…' : 'PDF'}
              </button>
            </div>
            {/* Report HTML is generated server-side from our own templates (trusted). */}
            <div
              className="report-preview p-6 md:p-8 overflow-auto opinion-body"
              dangerouslySetInnerHTML={{ __html: preview.html || '' }}
            />
          </div>
        )}
      </section>
    </div>
  )
}

function reportFilename(categories, yearStart, yearEnd) {
  const cat = categories.length === 1 ? categories[0] : `${categories.length}-issues`
  const yr = yearStart && yearEnd ? `_${yearStart}-${yearEnd}` : ''
  return `cert-layoff-report_${cat}${yr}.pdf`.replace(/[^a-z0-9_.-]/gi, '-')
}
