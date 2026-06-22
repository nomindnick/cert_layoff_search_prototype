import { useState } from 'react'
import { Link } from 'react-router-dom'
import { titleize, humanize, outcomeMeta } from '../lib/format'
import { track, getHolding } from '../lib/api'

/*
 * A single search result = one holding (PLAN.md §10 card).
 *   - outcome chip: green = district, amber = respondent, gray = mixed/none
 *   - issue category · subtype
 *   - "District (ALJ → profile) · year · OAH case"
 *   - house-style summary paragraph (summary_style_holding)
 *   - expandable detail: fetched on demand from /api/holding/{id}
 *     (facts / arguments / reasoning / authorities)
 *   - "open decision →" link
 *
 * HoldingHit shape (from /api/search):
 *   { holding_id, oah_case_no, district, alj, year,
 *     issue:{category,subtype,statement}, prevailing_party, remedies,
 *     summary_style_holding, rank }
 */
export default function HoldingCard({ hit }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState(false)

  const issue = hit.issue || {}
  const meta = outcomeMeta(hit.prevailing_party)
  const summary = hit.summary_style_holding || issue.statement || ''
  const remedies = (hit.remedies || []).filter(Boolean)

  function toggleExpand() {
    const next = !open
    setOpen(next)
    if (next) {
      track('expand_holding', { target_id: hit.holding_id, rank: hit.rank })
      if (!detail && !detailLoading) {
        setDetailLoading(true)
        setDetailError(false)
        getHolding(hit.holding_id)
          .then((d) => setDetail(d))
          .catch(() => setDetailError(true))
          .finally(() => setDetailLoading(false))
      }
    }
  }

  function onOpenDecision() {
    track('open_decision', { target_id: hit.oah_case_no, rank: hit.rank })
  }

  const statement = (detail && detail.issue && detail.issue.statement) || issue.statement
  const args = (detail && detail.arguments) || []
  const facts = (detail && detail.facts) || []
  const reasoning = (detail && detail.reasoning) || null
  const authorities = (detail && detail.authorities) || []
  const hasDetail = args.length || facts.length || (reasoning && reasoning.summary) || authorities.length

  return (
    <article className="rounded-xl border border-border bg-surface card-shadow card-shadow-hover transition-shadow animate-fade-in-up">
      <div className="p-4 sm:p-5">
        {/* Top row: outcome chip + issue label */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 mb-2.5">
          <OutcomeChip tone={meta.tone} label={meta.label} />
          <span className="text-sm text-text-secondary">
            {issue.category ? (
              <>
                <span className="font-medium text-text-primary">{titleize(issue.category)}</span>
                {issue.subtype ? <span className="text-text-muted"> · {titleize(issue.subtype)}</span> : null}
              </>
            ) : (
              <span className="text-text-muted">Uncategorized issue</span>
            )}
          </span>
        </div>

        {/* Provenance line — ALJ links to the scouting profile */}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.8rem] text-text-muted mb-3">
          {hit.district && <span className="text-text-secondary font-medium">{hit.district}</span>}
          {hit.alj && (
            <Link
              to={`/alj/${encodeURIComponent(hit.alj)}`}
              className="text-text-secondary hover:text-accent no-underline"
              title={`ALJ ${hit.alj} — scouting profile`}
            >
              ({hit.alj})
            </Link>
          )}
          {hit.year != null && (
            <>
              <Dot />
              <span className="tabular-nums">{hit.year}</span>
            </>
          )}
          {hit.oah_case_no && (
            <>
              <Dot />
              <span className="tabular-nums">OAH {hit.oah_case_no}</span>
            </>
          )}
        </div>

        {/* House-style paragraph */}
        {summary && <p className="holding-prose mb-3">{summary}</p>}

        {/* Remedies */}
        {remedies.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 mb-3">
            {remedies.map((r) => (
              <span
                key={r}
                className="inline-flex items-center rounded-md bg-surface-soft border border-border-light px-2 py-0.5 text-[0.7rem] text-text-secondary"
              >
                {humanize(r)}
              </span>
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-1">
          <button
            onClick={toggleExpand}
            className="inline-flex items-center gap-1 text-sm font-medium text-text-secondary hover:text-accent transition-colors"
            aria-expanded={open}
          >
            <svg
              className={`w-4 h-4 transition-transform ${open ? 'rotate-90' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 5l7 7-7 7" />
            </svg>
            {open ? 'Hide detail' : 'Detail'}
          </button>

          {hit.oah_case_no && (
            <Link
              to={`/decision/${encodeURIComponent(hit.oah_case_no)}`}
              onClick={onOpenDecision}
              className="ml-auto inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent-hover no-underline"
            >
              Open decision
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          )}
        </div>
      </div>

      {/* Expandable detail (fetched on demand) */}
      {open && (
        <div className="border-t border-border-light bg-surface-soft/60 px-4 sm:px-5 py-4 animate-fade-in">
          {detailLoading && <p className="text-sm text-text-muted">Loading detail…</p>}

          {!detailLoading && statement && (
            <DetailBlock title="Issue">
              <p className="text-sm text-text-primary leading-relaxed">{statement}</p>
            </DetailBlock>
          )}

          {!detailLoading && facts.length > 0 && (
            <DetailBlock title="Facts">
              <ul className="flex flex-col gap-1.5">
                {facts.map((f, i) => (
                  <li key={i} className="text-sm text-text-primary leading-relaxed">{f.summary}</li>
                ))}
              </ul>
            </DetailBlock>
          )}

          {!detailLoading && args.length > 0 && (
            <DetailBlock title="Arguments">
              <ul className="flex flex-col gap-2">
                {args.map((a, i) => (
                  <li key={i} className="text-sm text-text-primary leading-relaxed">
                    {a.party && (
                      <span className="font-medium text-text-secondary mr-1">{titleize(a.party)}:</span>
                    )}
                    {a.summary}
                  </li>
                ))}
              </ul>
            </DetailBlock>
          )}

          {!detailLoading && reasoning && reasoning.summary && (
            <DetailBlock title="Reasoning">
              <p className="text-sm text-text-primary leading-relaxed">{reasoning.summary}</p>
            </DetailBlock>
          )}

          {!detailLoading && authorities.length > 0 && (
            <DetailBlock title="Authorities">
              <ul className="flex flex-col gap-1">
                {authorities.map((c, i) => (
                  <li key={i} className="text-sm text-text-secondary leading-relaxed">
                    <span className="font-medium text-text-primary">{c.raw_cite}</span>
                    {c.proposition ? <span className="text-text-muted"> — {c.proposition}</span> : null}
                  </li>
                ))}
              </ul>
            </DetailBlock>
          )}

          {!detailLoading && !statement && !hasDetail && (
            <p className="text-sm text-text-muted">
              {detailError
                ? 'Could not load detail — open the decision to read the full holding.'
                : 'No additional detail recorded. Open the decision to read the full text.'}
            </p>
          )}
        </div>
      )}
    </article>
  )
}

function OutcomeChip({ tone, label }) {
  const styles = {
    district: 'bg-[var(--color-win-district-bg)] text-[var(--color-win-district)]',
    respondent: 'bg-[var(--color-win-respondent-bg)] text-[var(--color-win-respondent)]',
    mixed: 'bg-[var(--color-win-mixed-bg)] text-[var(--color-win-mixed)]',
  }
  const dot = {
    district: 'bg-[var(--color-win-district)]',
    respondent: 'bg-[var(--color-win-respondent)]',
    mixed: 'bg-[var(--color-win-mixed)]',
  }
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.7rem] font-semibold uppercase tracking-wide ${styles[tone]}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dot[tone]}`} />
      {label}
    </span>
  )
}

function DetailBlock({ title, children }) {
  return (
    <div className="mb-4 last:mb-0">
      <h4 className="eyebrow mb-1.5">{title}</h4>
      {children}
    </div>
  )
}

function Dot() {
  return <span className="text-text-muted/50">·</span>
}
