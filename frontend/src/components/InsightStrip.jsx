import { Link } from 'react-router-dom'
import { titleize, pct } from '../lib/format'

/*
 * The analytical heart of the app (PLAN.md §10). Given the `insight` object
 * from /api/search, render:
 *   - a win-rate bar (district share) with the corpus baseline marked, because
 *     the base rate is skewed ~79% district — the delta is the signal.
 *   - top sub-issues and most-active ALJs over the match set.
 *   - an inline-SVG sparkline of the per-year trend, split district vs respondent.
 *
 * Insight shape:
 *   { decision_count, holding_count, year_range:[min,max]|null,
 *     win_rate:{district,respondent,mixed,baseline_district},
 *     top_categories:[{name,count}], top_subtypes:[{name,count}],
 *     top_aljs:[{name,count}], trend:[{year,district,respondent,total}] }
 */
export default function InsightStrip({ insight, showAljs = true }) {
  if (!insight) return null

  const wr = insight.win_rate || {}
  const districtPct = pct(wr.district)
  const respondentPct = pct(wr.respondent)
  const baselinePct = pct(wr.baseline_district)

  const subtypes = (insight.top_subtypes || []).filter((s) => s && s.name)
  const aljs = (insight.top_aljs || []).filter((a) => a && a.name)
  const trend = (insight.trend || []).filter((t) => t && t.year != null)

  return (
    <section
      className="rounded-2xl border border-border bg-surface card-shadow p-5 md:p-6 animate-fade-in"
      aria-label="Insight summary"
    >
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8">
        {/* Win rate */}
        <div className="lg:col-span-5">
          <WinRateBar
            districtPct={districtPct}
            respondentPct={respondentPct}
            mixedPct={pct(wr.mixed)}
            baselinePct={baselinePct}
            holdingCount={insight.holding_count}
          />
        </div>

        {/* Sub-issues + ALJs */}
        <div className="lg:col-span-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-5">
          <ChipList title="Top sub-issues" items={subtypes} format={titleize} />
          {showAljs && <ChipList title="Most active ALJs" items={aljs} linkBase="/alj/" />}
        </div>

        {/* Trend sparkline */}
        <div className="lg:col-span-3">
          <TrendSparkline trend={trend} />
        </div>
      </div>
    </section>
  )
}

/* ── Win-rate bar with baseline marker ───────────────────────── */
function WinRateBar({ districtPct, respondentPct, mixedPct, baselinePct, holdingCount }) {
  const d = districtPct ?? 0
  const r = respondentPct ?? 0
  const m = mixedPct ?? Math.max(0, 100 - d - r)

  // Delta vs baseline framing — an elevated respondent rate is the story.
  let deltaNote = null
  if (districtPct != null && baselinePct != null) {
    const delta = districtPct - baselinePct
    if (delta <= -5) {
      deltaNote = {
        text: `Respondents win ${Math.abs(delta)} pts more often than the corpus baseline`,
        tone: 'text-[var(--color-win-respondent)]',
      }
    } else if (delta >= 5) {
      deltaNote = {
        text: `Districts win ${delta} pts more often than the corpus baseline`,
        tone: 'text-[var(--color-win-district)]',
      }
    } else {
      deltaNote = { text: 'In line with the corpus baseline', tone: 'text-text-muted' }
    }
  }

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span className="eyebrow">Who prevailed</span>
        {holdingCount != null && (
          <span className="text-xs text-text-muted tabular-nums">
            {holdingCount} ruled holding{holdingCount === 1 ? '' : 's'}
          </span>
        )}
      </div>

      <div className="flex items-baseline gap-2 mb-3">
        <span className="text-3xl font-semibold text-[var(--color-win-district)] tabular-nums">
          {districtPct != null ? `${districtPct}%` : '—'}
        </span>
        <span className="text-sm text-text-secondary">district</span>
        {respondentPct != null && (
          <span className="ml-auto text-sm text-text-secondary tabular-nums">
            <span className="text-[var(--color-win-respondent)] font-medium">{respondentPct}%</span> respondent
          </span>
        )}
      </div>

      {/* Stacked bar with a baseline tick overlaid */}
      <div className="relative h-3.5 rounded-full bg-[var(--color-win-mixed-bg)] overflow-hidden">
        <div
          className="absolute inset-y-0 left-0 bg-[var(--color-win-district)]"
          style={{ width: `${d}%` }}
        />
        <div
          className="absolute inset-y-0 bg-[var(--color-win-respondent)]"
          style={{ left: `${d}%`, width: `${r}%` }}
        />
        {m > 0 && (
          <div
            className="absolute inset-y-0 bg-[var(--color-win-mixed)]/40"
            style={{ left: `${d + r}%`, width: `${m}%` }}
          />
        )}
      </div>

      {/* Baseline marker line (sits below the bar, aligned to the district share) */}
      {baselinePct != null && (
        <div className="relative h-5 mt-1">
          <div
            className="absolute top-0 -translate-x-1/2 flex flex-col items-center"
            style={{ left: `${Math.min(98, Math.max(2, baselinePct))}%` }}
          >
            <span className="w-px h-2 bg-text-muted/70" />
            <span className="text-[0.65rem] text-text-muted whitespace-nowrap mt-0.5">
              baseline {baselinePct}%
            </span>
          </div>
        </div>
      )}

      {deltaNote && (
        <p className={`mt-2 text-xs font-medium ${deltaNote.tone}`}>{deltaNote.text}</p>
      )}
    </div>
  )
}

/* ── Ranked chip list (sub-issues, ALJs) ─────────────────────── */
function ChipList({ title, items, format, linkBase }) {
  return (
    <div>
      <span className="eyebrow block mb-2">{title}</span>
      {items.length === 0 ? (
        <span className="text-sm text-text-muted">—</span>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {items.slice(0, 4).map((it) => {
            const label = format ? format(it.name) : it.name
            return (
              <li key={it.name} className="flex items-center gap-2 text-sm">
                {linkBase ? (
                  <Link
                    to={`${linkBase}${encodeURIComponent(it.name)}`}
                    className="truncate text-text-primary hover:text-accent no-underline"
                    title={`${it.name} — scouting profile`}
                  >
                    {label}
                  </Link>
                ) : (
                  <span className="truncate text-text-primary">{label}</span>
                )}
                <span className="ml-auto text-xs text-text-muted tabular-nums shrink-0">{it.count}</span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

/* ── Inline-SVG trend sparkline, district vs respondent by year ── */
function TrendSparkline({ trend }) {
  const W = 220
  const H = 64
  const PAD = 4

  const years = trend.map((t) => t.year)
  const maxVal = Math.max(1, ...trend.map((t) => Math.max(t.district || 0, t.respondent || 0, t.total || 0)))

  function pathFor(key) {
    if (trend.length === 0) return ''
    if (trend.length === 1) {
      // A single year: draw a short flat tick so it's visible.
      const y = yScale(trend[0][key] || 0)
      return `M ${PAD} ${y} L ${W - PAD} ${y}`
    }
    return trend
      .map((t, i) => {
        const x = xScale(i)
        const y = yScale(t[key] || 0)
        return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
      })
      .join(' ')
  }

  function xScale(i) {
    if (trend.length <= 1) return W / 2
    return PAD + (i * (W - 2 * PAD)) / (trend.length - 1)
  }
  function yScale(v) {
    return H - PAD - (v / maxVal) * (H - 2 * PAD)
  }

  const yearRangeLabel =
    years.length > 0 ? `${years[0]}${years.length > 1 ? `–${years[years.length - 1]}` : ''}` : ''

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span className="eyebrow">Trend by year</span>
        {yearRangeLabel && <span className="text-xs text-text-muted tabular-nums">{yearRangeLabel}</span>}
      </div>

      {trend.length === 0 ? (
        <span className="text-sm text-text-muted">No yearly data</span>
      ) : (
        <>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            width="100%"
            height={H}
            role="img"
            aria-label="Holdings per year, district versus respondent wins"
            className="overflow-visible"
          >
            <path
              d={pathFor('district')}
              fill="none"
              stroke="var(--color-win-district)"
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <path
              d={pathFor('respondent')}
              fill="none"
              stroke="var(--color-win-respondent)"
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {/* End-point dots for legibility */}
            {trend.length > 0 && (
              <>
                <circle cx={xScale(trend.length - 1)} cy={yScale(trend[trend.length - 1].district || 0)} r="2.5" fill="var(--color-win-district)" />
                <circle cx={xScale(trend.length - 1)} cy={yScale(trend[trend.length - 1].respondent || 0)} r="2.5" fill="var(--color-win-respondent)" />
              </>
            )}
          </svg>
          <div className="flex items-center gap-4 mt-2 text-[0.7rem] text-text-secondary">
            <span className="inline-flex items-center gap-1.5">
              <span className="w-2.5 h-0.5 rounded bg-[var(--color-win-district)]" /> district
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="w-2.5 h-0.5 rounded bg-[var(--color-win-respondent)]" /> respondent
            </span>
          </div>
        </>
      )}
    </div>
  )
}
