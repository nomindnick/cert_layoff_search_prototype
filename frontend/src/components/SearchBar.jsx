import { useEffect, useRef, useState } from 'react'

/*
 * Natural-language or keyword query box. Controlled by the URL via `value`,
 * but holds local draft state so typing is snappy. Submits on Enter / button.
 */
export default function SearchBar({ value, onSearch, placeholder }) {
  const [draft, setDraft] = useState(value || '')
  const inputRef = useRef(null)

  // Keep the local draft in sync if the URL value changes externally
  // (e.g. clicking a category pill or navigating back).
  useEffect(() => {
    setDraft(value || '')
  }, [value])

  function submit(e) {
    e.preventDefault()
    onSearch(draft.trim())
    inputRef.current?.blur()
  }

  return (
    <form onSubmit={submit} role="search" className="relative">
      <div className="relative">
        <svg
          className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-text-muted"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
        </svg>
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={placeholder || 'Ask a question or search by issue — e.g. “skipping for special education credential”'}
          className="search-input w-full rounded-xl border border-border bg-surface pl-12 pr-28 py-3.5 text-[0.975rem] text-text-primary placeholder:text-text-muted focus:border-accent outline-none"
          aria-label="Search holdings"
          autoComplete="off"
          spellCheck="false"
        />
        <button
          type="submit"
          className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover transition-colors"
        >
          Search
        </button>
      </div>
    </form>
  )
}
