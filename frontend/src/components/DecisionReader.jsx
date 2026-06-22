import { Link } from 'react-router-dom'
import { titleize, humanize, formatDate, outcomeMeta } from '../lib/format'
import { track } from '../lib/api'

/*
 * In-app reader for a full decision record (DecisionDetail from
 * /api/decision/{case}). Renders a header (case/district/ALJ/date/outcome),
 * a board-action summary, the holdings list, the typeset full_text, and a
 * "Download original PDF" button (pdf_url on the record).
 *
 * Served record shape (de-identified at build time):
 *   { oah_case_no, district, alj, year, decision_date, school_year_affected,
 *     scope, decision_kind, overall,
 *     board_action:{fte_reduced, statutory_basis, services_reduced:[{description}]},
 *     n_respondents, holdings:[...], full_text, pdf_url }
 */
export default function DecisionReader({ record }) {
  if (!record) return null

  const board = record.board_action || {}
  const holdings = record.holdings || []
  const paragraphs = splitParagraphs(record.full_text)

  function onDownload() {
    track('download_pdf', { target_id: record.oah_case_no })
  }

  return (
    <article className="animate-fade-in">
      {/* ── Header ──────────────────────────────────────────── */}
      <header className="mb-8">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <OverallChip overall={record.overall} />
          {record.decision_kind && (
            <span className="text-xs text-text-muted uppercase tracking-wide">
              {titleize(record.decision_kind)}
            </span>
          )}
        </div>

        <h1 className="text-2xl md:text-[1.75rem] font-semibold text-text-heading leading-tight mb-2">
          {record.district || 'Decision'}
        </h1>

        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm text-text-secondary">
          {record.alj && (
            <Link
              to={`/alj/${encodeURIComponent(record.alj)}`}
              className="text-text-secondary hover:text-accent no-underline"
              title={`ALJ ${record.alj} — scouting profile`}
            >
              ALJ {record.alj}
            </Link>
          )}
          {record.decision_date && (
            <>
              <Dot />
              <span>{formatDate(record.decision_date) || record.decision_date}</span>
            </>
          )}
          {!record.decision_date && record.year != null && (
            <>
              <Dot />
              <span className="tabular-nums">{record.year}</span>
            </>
          )}
          {record.oah_case_no && (
            <>
              <Dot />
              <span className="tabular-nums">OAH {record.oah_case_no}</span>
            </>
          )}
          {record.school_year_affected && (
            <>
              <Dot />
              <span>SY {record.school_year_affected}</span>
            </>
          )}
        </div>

        {record.pdf_url && (
          <a
            href={record.pdf_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={onDownload}
            className="inline-flex items-center gap-1.5 mt-4 px-3.5 py-2 rounded-lg border border-accent text-accent text-sm font-medium hover:bg-accent-light transition-colors no-underline"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M12 4v12m0 0l-4-4m4 4l4-4M4 20h16" />
            </svg>
            Download original PDF
          </a>
        )}
      </header>

      {/* ── Board action summary ────────────────────────────── */}
      {(board.fte_reduced != null || board.statutory_basis || (board.services_reduced || []).length > 0 || record.n_respondents != null) && (
        <section className="mb-8 rounded-xl border border-border bg-surface card-shadow p-5">
          <h2 className="eyebrow mb-3">Board action</h2>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
            {board.fte_reduced != null && (
              <Field label="FTE reduced" value={renderFte(board.fte_reduced)} />
            )}
            {record.n_respondents != null && (
              <Field label="Respondents" value={String(record.n_respondents)} />
            )}
            {board.statutory_basis && (
              <Field label="Statutory basis" value={renderStatutory(board.statutory_basis)} />
            )}
            {record.scope && <Field label="Scope" value={titleize(record.scope)} />}
          </dl>

          {(board.services_reduced || []).length > 0 && (
            <div className="mt-4">
              <span className="filter-label">Services reduced</span>
              <ul className="flex flex-wrap gap-1.5 mt-1">
                {board.services_reduced.map((s, i) => (
                  <li
                    key={i}
                    className="inline-flex items-center rounded-md bg-surface-soft border border-border-light px-2 py-0.5 text-xs text-text-secondary"
                  >
                    {s.description || humanize(s)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {/* ── Holdings ─────────────────────────────────────────── */}
      {holdings.length > 0 && (
        <section className="mb-10">
          <h2 className="text-lg font-semibold text-text-heading mb-4">
            Holdings <span className="text-text-muted font-normal">({holdings.length})</span>
          </h2>
          <ol className="flex flex-col gap-4">
            {holdings.map((h, i) => (
              <HoldingItem key={h.idx ?? i} holding={h} n={i + 1} />
            ))}
          </ol>
        </section>
      )}

      {/* ── Full text ────────────────────────────────────────── */}
      {paragraphs.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-text-heading mb-4">Full text</h2>
          <div className="rounded-xl border border-border bg-surface card-shadow p-6 md:p-8">
            <div className="opinion-body max-w-[68ch]">
              {paragraphs.map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
          </div>
        </section>
      )}
    </article>
  )
}

/* ── Per-holding block in the reader ─────────────────────────── */
function HoldingItem({ holding, n }) {
  const issue = holding.issue || {}
  const meta = outcomeMeta(holding.prevailing_party)
  const args = holding.arguments || []
  const reasoning = holding.reasoning || {}
  const authorities = holding.authorities || []
  const facts = holding.facts || []
  const remedies = (holding.remedies || []).filter(Boolean)

  return (
    <li className="rounded-xl border border-border bg-surface card-shadow p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 mb-2">
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-surface-soft border border-border-light text-xs font-semibold text-text-secondary tabular-nums">
          {n}
        </span>
        <ChipSmall tone={meta.tone} label={meta.label} />
        {issue.category && (
          <span className="text-sm text-text-secondary">
            <span className="font-medium text-text-primary">{titleize(issue.category)}</span>
            {issue.subtype ? <span className="text-text-muted"> · {titleize(issue.subtype)}</span> : null}
          </span>
        )}
      </div>

      {holding.summary_style_holding && (
        <p className="holding-prose mb-3">{holding.summary_style_holding}</p>
      )}

      {issue.statement && !holding.summary_style_holding && (
        <p className="text-sm text-text-primary leading-relaxed mb-3">{issue.statement}</p>
      )}

      {remedies.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          {remedies.map((r) => (
            <span key={r} className="inline-flex items-center rounded-md bg-surface-soft border border-border-light px-2 py-0.5 text-[0.7rem] text-text-secondary">
              {humanize(r)}
            </span>
          ))}
        </div>
      )}

      {(args.length > 0 || (reasoning && reasoning.summary) || authorities.length > 0 || facts.length > 0) && (
        <details className="group mt-1">
          <summary className="cursor-pointer list-none inline-flex items-center gap-1 text-sm font-medium text-text-secondary hover:text-accent">
            <svg className="w-4 h-4 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 5l7 7-7 7" />
            </svg>
            Detail
          </summary>
          <div className="mt-3 pl-1">
            {facts.length > 0 && (
              <Block title="Facts">
                <ul className="flex flex-col gap-1.5">
                  {facts.map((f, i) => (
                    <li key={i} className="text-sm text-text-primary leading-relaxed">{f.summary}</li>
                  ))}
                </ul>
              </Block>
            )}
            {args.length > 0 && (
              <Block title="Arguments">
                <ul className="flex flex-col gap-1.5">
                  {args.map((a, i) => (
                    <li key={i} className="text-sm text-text-primary leading-relaxed">
                      {a.party && <span className="font-medium text-text-secondary mr-1">{titleize(a.party)}:</span>}
                      {a.summary}
                    </li>
                  ))}
                </ul>
              </Block>
            )}
            {reasoning && reasoning.summary && (
              <Block title="Reasoning">
                <p className="text-sm text-text-primary leading-relaxed">{reasoning.summary}</p>
              </Block>
            )}
            {authorities.length > 0 && (
              <Block title="Authorities">
                <ul className="flex flex-col gap-1">
                  {authorities.map((c, i) => (
                    <li key={i} className="text-sm text-text-secondary leading-relaxed">
                      <span className="font-medium text-text-primary">{c.raw_cite}</span>
                      {c.proposition ? <span className="text-text-muted"> — {c.proposition}</span> : null}
                    </li>
                  ))}
                </ul>
              </Block>
            )}
          </div>
        </details>
      )}
    </li>
  )
}

/* ── small helpers ───────────────────────────────────────────── */

function Field({ label, value }) {
  return (
    <div>
      <dt className="filter-label">{label}</dt>
      <dd className="text-sm text-text-primary">{value}</dd>
    </div>
  )
}

function Block({ title, children }) {
  return (
    <div className="mb-3 last:mb-0">
      <h5 className="eyebrow mb-1">{title}</h5>
      {children}
    </div>
  )
}

function OverallChip({ overall }) {
  const styles = {
    district: 'bg-[var(--color-win-district-bg)] text-[var(--color-win-district)]',
    respondent: 'bg-[var(--color-win-respondent-bg)] text-[var(--color-win-respondent)]',
    mixed: 'bg-[var(--color-win-mixed-bg)] text-[var(--color-win-mixed)]',
  }
  // The chip is keyed on outcome.overall (sustained/not_sustained/...), NOT on a
  // prevailing_party, so it carries its own tone map: sustained -> district
  // (the district's reduction held), not_sustained -> respondent, partial/unknown -> mixed.
  const tone = toneForOverall(overall)
  const label = labelForOverall(overall)
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${styles[tone]}`}>
      {label}
    </span>
  )
}

function ChipSmall({ tone, label }) {
  const styles = {
    district: 'bg-[var(--color-win-district-bg)] text-[var(--color-win-district)]',
    respondent: 'bg-[var(--color-win-respondent-bg)] text-[var(--color-win-respondent)]',
    mixed: 'bg-[var(--color-win-mixed-bg)] text-[var(--color-win-mixed)]',
  }
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[0.68rem] font-semibold uppercase tracking-wide ${styles[tone]}`}>
      {label}
    </span>
  )
}

function toneForOverall(overall) {
  switch (overall) {
    case 'sustained':
      return 'district'
    case 'not_sustained':
      return 'respondent'
    default:
      return 'mixed'
  }
}

function labelForOverall(overall) {
  switch (overall) {
    case 'sustained':
      return 'Sustained'
    case 'sustained_in_part':
      return 'Sustained in part'
    case 'not_sustained':
      return 'Not sustained'
    default:
      return 'Outcome unknown'
  }
}

function renderFte(fte) {
  if (fte == null) return '—'
  if (typeof fte === 'object') {
    const parts = []
    if (fte.regular != null) parts.push(`${fte.regular} regular`)
    if (fte.temporary != null) parts.push(`${fte.temporary} temporary`)
    return parts.length ? parts.join(', ') : '—'
  }
  return String(fte)
}

function renderStatutory(basis) {
  if (Array.isArray(basis)) return basis.join(', ')
  return String(basis)
}

function splitParagraphs(text) {
  if (!text) return []
  return String(text)
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean)
}

function Dot() {
  return <span className="text-text-muted/50">·</span>
}
