import { useEffect, useRef, useState } from 'react'
import { titleize } from '../lib/format'

/*
 * Filter controls for the search results: category multi-select, year range,
 * district, ALJ, and prevailing-party. Values come in as props (URL-derived);
 * changes are pushed up via the on* callbacks. The parent owns URL state.
 *
 * `facets` is the /api/facets payload:
 *   { categories:[{key,label,count}], year_min, year_max,
 *     districts:[{name,count}], aljs:[{name,count}] }
 */
export default function FilterBar({
  facets,
  categories,
  yearStart,
  yearEnd,
  district,
  alj,
  prevailingParty,
  onCategoriesChange,
  onYearChange,
  onDistrictChange,
  onAljChange,
  onPrevailingPartyChange,
  onClearAll,
}) {
  const catList = facets?.categories || []
  const districtList = facets?.districts || []
  const aljList = facets?.aljs || []

  const activeCount =
    categories.length +
    (yearStart ? 1 : 0) +
    (yearEnd ? 1 : 0) +
    (district ? 1 : 0) +
    (alj ? 1 : 0) +
    (prevailingParty ? 1 : 0)

  return (
    <div className="rounded-xl border border-border bg-surface card-shadow">
      <div className="flex flex-wrap items-end gap-3 p-3.5">
        <CategoryMultiSelect
          options={catList}
          selected={categories}
          onChange={onCategoriesChange}
        />

        <YearRange
          min={facets?.year_min}
          max={facets?.year_max}
          start={yearStart}
          end={yearEnd}
          onChange={onYearChange}
        />

        <ComboFilter
          label="District"
          placeholder="Any district"
          value={district}
          options={districtList}
          onChange={onDistrictChange}
        />

        <ComboFilter
          label="ALJ"
          placeholder="Any ALJ"
          value={alj}
          options={aljList}
          onChange={onAljChange}
        />

        <div>
          <span className="filter-label">Prevailing party</span>
          <select
            value={prevailingParty || ''}
            onChange={(e) => onPrevailingPartyChange(e.target.value || null)}
            className="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary outline-none focus:border-accent min-w-[9rem]"
          >
            <option value="">Any outcome</option>
            <option value="district">District prevailed</option>
            <option value="respondent">Respondent prevailed</option>
            <option value="mixed">Mixed</option>
          </select>
        </div>

        {activeCount > 0 && (
          <button
            onClick={onClearAll}
            className="ml-auto self-center text-xs font-medium text-text-secondary hover:text-accent underline underline-offset-2"
          >
            Clear all ({activeCount})
          </button>
        )}
      </div>
    </div>
  )
}

/* ── Category multi-select (popover with checkboxes) ──────────── */
function CategoryMultiSelect({ options, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function onDoc(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  function toggle(key) {
    if (selected.includes(key)) onChange(selected.filter((k) => k !== key))
    else onChange([...selected, key])
  }

  const label =
    selected.length === 0
      ? 'All issues'
      : selected.length === 1
        ? labelFor(options, selected[0])
        : `${selected.length} issues`

  return (
    <div className="relative" ref={ref}>
      <span className="filter-label">Issue category</span>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary outline-none focus:border-accent min-w-[11rem]"
        aria-expanded={open}
      >
        <span className={selected.length ? 'text-text-primary' : 'text-text-muted'}>{label}</span>
        <svg className="ml-auto w-4 h-4 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute z-40 mt-2 w-72 max-h-80 overflow-auto rounded-xl border border-border bg-surface p-1.5 card-shadow animate-fade-in">
          {options.length === 0 && (
            <div className="px-3 py-2 text-sm text-text-muted">No categories</div>
          )}
          {options.map((opt) => {
            const checked = selected.includes(opt.key)
            return (
              <label
                key={opt.key}
                className="flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg hover:bg-surface-soft cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(opt.key)}
                  className="accent-[var(--color-accent)] w-4 h-4"
                />
                <span className="flex-1 text-sm text-text-primary">{opt.label || titleize(opt.key)}</span>
                {opt.count != null && (
                  <span className="text-xs text-text-muted tabular-nums">{opt.count}</span>
                )}
              </label>
            )
          })}
          {selected.length > 0 && (
            <button
              onClick={() => onChange([])}
              className="w-full mt-1 px-2.5 py-1.5 text-xs font-medium text-text-secondary hover:text-accent text-left"
            >
              Clear selection
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function labelFor(options, key) {
  const found = options.find((o) => o.key === key)
  return found?.label || titleize(key)
}

/* ── Year range ──────────────────────────────────────────────── */
function YearRange({ min, max, start, end, onChange }) {
  return (
    <div>
      <span className="filter-label">Years</span>
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          inputMode="numeric"
          value={start ?? ''}
          min={min}
          max={max}
          placeholder={min != null ? String(min) : 'From'}
          onChange={(e) => onChange({ start: e.target.value ? parseInt(e.target.value, 10) : null, end })}
          className="w-20 rounded-lg border border-border bg-surface px-2.5 py-2 text-sm text-text-primary outline-none focus:border-accent tabular-nums"
          aria-label="Year from"
        />
        <span className="text-text-muted text-sm">–</span>
        <input
          type="number"
          inputMode="numeric"
          value={end ?? ''}
          min={min}
          max={max}
          placeholder={max != null ? String(max) : 'To'}
          onChange={(e) => onChange({ start, end: e.target.value ? parseInt(e.target.value, 10) : null })}
          className="w-20 rounded-lg border border-border bg-surface px-2.5 py-2 text-sm text-text-primary outline-none focus:border-accent tabular-nums"
          aria-label="Year to"
        />
      </div>
    </div>
  )
}

/* ── District / ALJ combo (text input with datalist suggestions) ── */
function ComboFilter({ label, placeholder, value, options, onChange }) {
  const listId = `combo-${label.toLowerCase()}`
  const [draft, setDraft] = useState(value || '')

  useEffect(() => {
    setDraft(value || '')
  }, [value])

  function commit(v) {
    const trimmed = (v || '').trim()
    onChange(trimmed || null)
  }

  return (
    <div>
      <span className="filter-label">{label}</span>
      <input
        list={listId}
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => commit(draft)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            commit(draft)
          }
        }}
        className="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary outline-none focus:border-accent min-w-[10rem]"
      />
      <datalist id={listId}>
        {(options || []).slice(0, 200).map((o) => (
          <option key={o.name} value={o.name}>
            {o.count != null ? `${o.name} (${o.count})` : o.name}
          </option>
        ))}
      </datalist>
    </div>
  )
}
