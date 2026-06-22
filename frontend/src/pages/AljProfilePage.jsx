import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import InsightStrip from '../components/InsightStrip'
import { getAlj, track } from '../lib/api'
import { titleize, pct, outcomeMeta } from '../lib/format'

/*
 * ALJ scouting profile ("who's my judge"). Fetches /api/alj/{name} and renders
 * caseload + win-rate (reusing InsightStrip), a per-issue breakdown with the
 * district win-rate, and a few representative holdings. The headline
 * differentiator — no public tool offers this.
 */
export default function AljProfilePage() {
  const { name } = useParams()
  const navigate = useNavigate()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    setLoading(true)
    setNotFound(false)
    setError(false)
    const c = new AbortController()
    getAlj(name, c.signal)
      .then((data) => {
        setProfile(data)
        setLoading(false)
        track('page_view', { target_id: `/alj/${name}` })
      })
      .catch((err) => {
        if (err.name === 'AbortError' || err.status === 401) return
        if (err.status === 404) setNotFound(true)
        else setError(true)
        setLoading(false)
      })
    window.scrollTo(0, 0)
    return () => c.abort()
  }, [name])

  const insight = profile && {
    decision_count: profile.n_decisions,
    holding_count: profile.n_holdings,
    year_range: profile.year_range,
    win_rate: profile.win_rate,
    top_subtypes: profile.top_subtypes || [],
    top_aljs: [],
    top_categories: [],
    trend: profile.trend || [],
  }

  return (
    <div>
      <button
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-1 text-sm font-medium text-text-secondary hover:text-accent mb-6"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15 19l-7-7 7-7" />
        </svg>
        Back
      </button>

      {loading ? (
        <Skeleton />
      ) : notFound ? (
        <Message title="ALJ not found" body={`No layoff decisions in the corpus are attributed to “${name}”.`} />
      ) : error ? (
        <Message title="Couldn’t load this profile" body="An unexpected error occurred. Please try again shortly." />
      ) : (
        <article className="animate-fade-in">
          {/* Header */}
          <header className="mb-7">
            <span className="eyebrow">Administrative Law Judge · scouting profile</span>
            <h1 className="text-2xl md:text-[1.85rem] font-semibold text-text-heading leading-tight mt-1 mb-2">
              {profile.name}
            </h1>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-text-secondary">
              <Stat n={profile.n_decisions} unit="decision" />
              <Dot />
              <Stat n={profile.n_holdings} unit="holding" />
              <Dot />
              <Stat n={profile.n_districts} unit="district" />
              {profile.year_range && (
                <>
                  <Dot />
                  <span className="tabular-nums">
                    {profile.year_range[0]}
                    {profile.year_range[1] !== profile.year_range[0] ? `–${profile.year_range[1]}` : ''}
                  </span>
                </>
              )}
            </div>
          </header>

          {/* Win-rate + trend (reuse the dashboard insight strip; ALJ column moot) */}
          {insight && (
            <div className="mb-8">
              <InsightStrip insight={insight} showAljs={false} />
            </div>
          )}

          {/* Per-issue breakdown */}
          {(profile.issues || []).length > 0 && (
            <section className="mb-8">
              <h2 className="text-lg font-semibold text-text-heading mb-4">Issues ruled on</h2>
              <div className="rounded-xl border border-border bg-surface card-shadow divide-y divide-border-light">
                {profile.issues.map((it) => (
                  <IssueRow key={it.category} issue={it} />
                ))}
              </div>
            </section>
          )}

          {/* Representative holdings */}
          {(profile.samples || []).length > 0 && (
            <section>
              <h2 className="text-lg font-semibold text-text-heading mb-1">Representative holdings</h2>
              <p className="text-sm text-text-muted mb-4">Respondent wins and flagged-notable holdings first.</p>
              <ol className="flex flex-col gap-3">
                {profile.samples.map((s, i) => (
                  <SampleCard key={i} sample={s} />
                ))}
              </ol>
            </section>
          )}
        </article>
      )}
    </div>
  )
}

/* ── Per-issue row with a district/respondent win-rate bar ────── */
function IssueRow({ issue }) {
  const d = issue.district_win_rate
  const r = issue.respondent_win_rate
  const dPct = pct(d)
  const rPct = pct(r)
  return (
    <div className="flex items-center gap-4 px-4 py-3">
      <span className="text-sm text-text-primary font-medium w-44 shrink-0 truncate">
        {titleize(issue.category)}
      </span>
      <span className="text-xs text-text-muted tabular-nums w-10 shrink-0">{issue.n}×</span>
      <div className="flex-1 min-w-0">
        {dPct != null ? (
          <div className="relative h-2.5 rounded-full bg-[var(--color-win-mixed-bg)] overflow-hidden">
            <div className="absolute inset-y-0 left-0 bg-[var(--color-win-district)]" style={{ width: `${dPct}%` }} />
            <div
              className="absolute inset-y-0 bg-[var(--color-win-respondent)]"
              style={{ left: `${dPct}%`, width: `${rPct ?? 0}%` }}
            />
          </div>
        ) : (
          <span className="text-xs text-text-muted">no ruled holdings</span>
        )}
      </div>
      <span className="text-xs tabular-nums w-28 shrink-0 text-right">
        {dPct != null ? (
          <>
            <span className="text-[var(--color-win-district)] font-medium">{dPct}%</span>
            <span className="text-text-muted"> district</span>
          </>
        ) : (
          '—'
        )}
      </span>
    </div>
  )
}

/* ── Representative-holding card ──────────────────────────────── */
function SampleCard({ sample }) {
  const meta = outcomeMeta(sample.prevailing_party)
  const styles = {
    district: 'bg-[var(--color-win-district-bg)] text-[var(--color-win-district)]',
    respondent: 'bg-[var(--color-win-respondent-bg)] text-[var(--color-win-respondent)]',
    mixed: 'bg-[var(--color-win-mixed-bg)] text-[var(--color-win-mixed)]',
  }
  return (
    <li className="rounded-xl border border-border bg-surface card-shadow p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mb-2">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[0.68rem] font-semibold uppercase tracking-wide ${styles[meta.tone]}`}>
          {meta.label}
        </span>
        {sample.category && (
          <span className="text-sm text-text-secondary">
            <span className="font-medium text-text-primary">{titleize(sample.category)}</span>
            {sample.subtype ? <span className="text-text-muted"> · {titleize(sample.subtype)}</span> : null}
          </span>
        )}
        <span className="ml-auto text-[0.78rem] text-text-muted">
          {sample.district}
          {sample.year != null ? ` · ${sample.year}` : ''}
        </span>
      </div>
      {sample.summary && <p className="holding-prose mb-2.5">{sample.summary}</p>}
      {sample.oah_case_no && (
        <Link
          to={`/decision/${encodeURIComponent(sample.oah_case_no)}`}
          className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent-hover no-underline"
        >
          Open decision
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 5l7 7-7 7" />
          </svg>
        </Link>
      )}
    </li>
  )
}

/* ── small helpers ───────────────────────────────────────────── */
function Stat({ n, unit }) {
  return (
    <span>
      <span className="font-medium text-text-primary tabular-nums">{n}</span> {unit}
      {n === 1 ? '' : 's'}
    </span>
  )
}

function Dot() {
  return <span className="text-text-muted/50">·</span>
}

function Message({ title, body }) {
  return (
    <div className="text-center py-16 animate-fade-in">
      <h1 className="text-lg font-semibold text-text-primary mb-2">{title}</h1>
      <p className="text-text-secondary text-sm max-w-md mx-auto mb-6">{body}</p>
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-accent border border-accent rounded-lg hover:bg-accent-light transition-colors no-underline"
      >
        Back to search
      </Link>
    </div>
  )
}

function Skeleton() {
  return (
    <div aria-hidden="true" className="animate-pulse">
      <div className="h-4 w-48 bg-border-light rounded mb-3" />
      <div className="h-8 w-1/3 bg-border-light rounded mb-3" />
      <div className="h-4 w-1/2 bg-border-light rounded mb-8" />
      <div className="h-40 w-full bg-border-light rounded mb-6" />
      <div className="h-48 w-full bg-border-light rounded" />
    </div>
  )
}
