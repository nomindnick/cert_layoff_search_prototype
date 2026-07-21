import { useEffect, useState } from 'react'
import { getAdminStats } from '../lib/api'
import { humanize } from '../lib/format'

/*
 * Admin-only usage dashboard (/admin), gated server-side by ADMIN_TOKENS and
 * hidden from the nav for everyone else.
 *
 * The page leads with per-person tiles rather than a chart, because the
 * question it exists to answer ("has <person> actually opened this yet?") is a
 * one-bit answer that a chart would bury. Everyone in ACCESS_TOKENS is listed
 * whether or not they have any events — a never-used link is the finding.
 *
 * The activity strip is a single series, so it carries no legend and uses the
 * one accent hue; identity is never encoded by color anywhere on this page.
 */
export default function AdminPage() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    getAdminStats(controller.signal)
      .then(setStats)
      .catch((err) => {
        if (err?.name === 'AbortError') return
        setError(
          err?.status === 403
            ? 'This page is admin-only. Your token is valid but is not listed in ADMIN_TOKENS.'
            : 'Could not load usage stats.'
        )
      })
    return () => controller.abort()
  }, [])

  if (error) {
    return (
      <div className="max-w-2xl mx-auto py-16 text-center">
        <h2 className="text-xl font-semibold text-text-heading mb-2">Usage</h2>
        <p className="text-text-secondary">{error}</p>
      </div>
    )
  }

  if (!stats) {
    return <p className="text-text-muted py-16 text-center animate-pulse">Loading usage…</p>
  }

  if (stats.ok === false) {
    return (
      <div className="max-w-2xl mx-auto py-16 text-center">
        <h2 className="text-xl font-semibold text-text-heading mb-2">Usage</h2>
        <p className="text-text-secondary">
          The analytics store is unavailable ({stats.error || 'unknown error'}).
        </p>
      </div>
    )
  }

  const people = stats.people || []
  const ct = stats.click_through || {}

  return (
    <div className="animate-fade-in space-y-8">
      <header>
        <h2 className="text-2xl font-semibold text-text-heading mb-1">Usage</h2>
        <p className="text-text-secondary text-sm">
          {stats.total_events?.toLocaleString() || 0} events
          {stats.first_event && stats.last_event && (
            <>
              {' '}· {shortDate(stats.first_event)} – {shortDate(stats.last_event)}
            </>
          )}
        </p>
      </header>

      {/* ── Who has actually used it ─────────────────────────── */}
      <section aria-label="Per person">
        <h3 className="eyebrow mb-3">Per person</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {people.map((p) => (
            <PersonCard key={p.name} person={p} />
          ))}
        </div>
      </section>

      {/* ── Activity over time ───────────────────────────────── */}
      {(stats.activity || []).length > 0 && (
        <section aria-label="Activity by day">
          <h3 className="eyebrow mb-3">Activity by day</h3>
          <ActivityChart data={stats.activity} />
        </section>
      )}

      {/* ── Engagement + event mix ───────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section
          aria-label="Click-through"
          className="rounded-2xl border border-border bg-surface card-shadow p-5"
        >
          <h3 className="eyebrow mb-3">Search → click</h3>
          <div className="flex items-baseline gap-6 flex-wrap">
            <Stat value={ct.searches ?? 0} label="searches" />
            <Stat value={ct.clicks ?? 0} label="result clicks" />
            <Stat
              value={ct.avg_rank == null ? '—' : ct.avg_rank}
              label="avg clicked rank"
            />
          </div>
          <p className="text-xs text-text-muted mt-3 leading-relaxed">
            Every search logs its ranked results and every click logs the target — this is
            the leakage-free relevance pool for evaluating ranking.
          </p>
        </section>

        <section
          aria-label="Activity by type"
          className="rounded-2xl border border-border bg-surface card-shadow p-5"
        >
          <h3 className="eyebrow mb-3">Activity by type</h3>
          <CountRows
            rows={(stats.by_type || []).map((r) => ({
              label: humanize(r.event_type),
              count: r.count,
            }))}
          />
        </section>
      </div>

      {/* ── What they searched ───────────────────────────────── */}
      <section
        aria-label="Top searches"
        className="rounded-2xl border border-border bg-surface card-shadow p-5"
      >
        <h3 className="eyebrow mb-3">Top searches</h3>
        {(stats.top_searches || []).length === 0 ? (
          <p className="text-sm text-text-muted">No text searches logged yet.</p>
        ) : (
          <ul className="divide-y divide-border-light">
            {stats.top_searches.map((s) => (
              <li key={s.query} className="py-2 flex items-baseline gap-3 text-sm">
                <span className="tabular-nums text-text-muted w-8 shrink-0">{s.count}×</span>
                <span className="text-text-primary flex-1 break-words">{s.query}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── Raw feed ─────────────────────────────────────────── */}
      <section
        aria-label="Recent activity"
        className="rounded-2xl border border-border bg-surface card-shadow p-5"
      >
        <h3 className="eyebrow mb-3">Recent activity</h3>
        <div className="overflow-x-auto -mx-5 px-5">
          <table className="w-full text-sm min-w-[34rem]">
            <thead>
              <tr className="text-left text-xs text-text-muted border-b border-border-light">
                <th className="font-medium pb-2 pr-4">When</th>
                <th className="font-medium pb-2 pr-4">Who</th>
                <th className="font-medium pb-2 pr-4">What</th>
                <th className="font-medium pb-2">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light">
              {(stats.recent || []).map((r, i) => (
                <tr key={i}>
                  <td className="py-2 pr-4 whitespace-nowrap text-text-muted tabular-nums">
                    {shortDateTime(r.ts)}
                  </td>
                  <td className="py-2 pr-4 whitespace-nowrap text-text-primary">{r.user}</td>
                  <td className="py-2 pr-4 whitespace-nowrap text-text-secondary">
                    {humanize(r.event_type)}
                    {r.referrer === 'mcp' && (
                      <span className="ml-1.5 text-[0.65rem] uppercase tracking-wide text-accent">
                        mcp
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-text-secondary break-words">{r.what}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

/* ── Per-person tile ────────────────────────────────────────── */
function PersonCard({ person }) {
  const used = person.events > 0
  return (
    <div
      className={
        'rounded-2xl border bg-surface card-shadow p-4 ' +
        (used ? 'border-border' : 'border-dashed border-border')
      }
    >
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <span className="font-medium text-text-heading">{person.name}</span>
        {person.shared && (
          <span
            className="text-[0.65rem] uppercase tracking-wide text-win-respondent"
            title={`Seen from ${person.distinct_ips} different networks — the link may have been forwarded`}
          >
            shared?
          </span>
        )}
      </div>

      {used ? (
        <>
          <div className="text-2xl font-semibold text-text-heading tabular-nums leading-none mb-1">
            {timeAgo(person.last_seen)}
          </div>
          <div className="text-xs text-text-muted">
            {person.events.toLocaleString()} events · {person.sessions} session
            {person.sessions === 1 ? '' : 's'} · {person.active_days} active day
            {person.active_days === 1 ? '' : 's'}
          </div>
        </>
      ) : (
        <>
          <div className="text-2xl font-semibold text-text-muted leading-none mb-1">
            Never opened
          </div>
          <div className="text-xs text-text-muted">No events logged for this link.</div>
        </>
      )}
    </div>
  )
}

/* ── Single-series daily activity ───────────────────────────── */
function ActivityChart({ data }) {
  const max = Math.max(...data.map((d) => d.count), 1)
  const activeDays = data.filter((d) => d.count > 0).length
  return (
    <div className="rounded-2xl border border-border bg-surface card-shadow p-5">
      {/* The series is zero-filled server-side, so an idle day is a real gap.
          A zero renders as NO bar against the baseline rule — giving it a
          minimum height would make "nobody came" look like "somebody came". */}
      <div
        className="flex items-end gap-[2px] h-32 overflow-x-auto border-b border-border"
        role="img"
        aria-label={`Events per day over the last ${data.length} days; ${activeDays} day${
          activeDays === 1 ? '' : 's'
        } with any activity, peak ${max} in a day`}
      >
        {data.map((d) => (
          <div
            key={d.day}
            className={
              'flex-1 min-w-[3px] rounded-t-[4px] transition-colors ' +
              (d.count > 0 ? 'bg-accent hover:bg-accent-hover' : 'bg-transparent')
            }
            style={{ height: d.count > 0 ? `${Math.max((d.count / max) * 100, 3)}%` : '0%' }}
            title={`${d.day}: ${d.count} event${d.count === 1 ? '' : 's'}`}
          />
        ))}
      </div>
      <div className="flex justify-between text-xs text-text-muted mt-2 tabular-nums">
        <span>{data[0]?.day}</span>
        <span className="text-text-secondary">
          {activeDays} active day{activeDays === 1 ? '' : 's'} · peak {max}
        </span>
        <span>{data[data.length - 1]?.day}</span>
      </div>
    </div>
  )
}

/* ── Small pieces ───────────────────────────────────────────── */
function Stat({ value, label }) {
  return (
    <div>
      <div className="text-2xl font-semibold text-text-heading tabular-nums leading-none">
        {typeof value === 'number' ? value.toLocaleString() : value}
      </div>
      <div className="text-xs text-text-muted mt-1">{label}</div>
    </div>
  )
}

function CountRows({ rows }) {
  if (!rows.length) return <p className="text-sm text-text-muted">Nothing logged yet.</p>
  const max = Math.max(...rows.map((r) => r.count), 1)
  return (
    <ul className="space-y-1.5">
      {rows.map((r) => (
        <li key={r.label} className="flex items-center gap-3 text-sm">
          <span className="text-text-primary w-32 shrink-0 truncate">{r.label}</span>
          <span className="flex-1 h-2 bg-surface-soft rounded-full overflow-hidden">
            <span
              className="block h-full bg-accent rounded-full"
              style={{ width: `${(r.count / max) * 100}%` }}
            />
          </span>
          <span className="tabular-nums text-text-muted w-10 text-right">{r.count}</span>
        </li>
      ))}
    </ul>
  )
}

/* ── Date helpers ───────────────────────────────────────────── */
function shortDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d) ? String(iso).slice(0, 10) : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function shortDateTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return String(iso).slice(0, 16)
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function timeAgo(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return '—'
  const mins = Math.floor((Date.now() - d.getTime()) / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  return months < 12 ? `${months}mo ago` : `${Math.floor(months / 12)}y ago`
}
