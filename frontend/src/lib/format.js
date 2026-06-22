/*
 * Small pure formatting helpers shared across components.
 * All tolerate null/undefined — the corpus has gaps everywhere.
 */

// "skipping_criteria" / "skipping-criteria" -> "Skipping Criteria"
export function titleize(s) {
  if (!s) return ''
  return String(s)
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

// Sentence-case a raw key without forcing every word capitalized.
export function humanize(s) {
  if (!s) return ''
  const t = String(s).replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
  return t.charAt(0).toUpperCase() + t.slice(1)
}

export function formatDate(dateStr) {
  if (!dateStr) return null
  const d = new Date(String(dateStr).slice(0, 10) + 'T00:00:00')
  if (isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
}

// Strip a leading "N" from an OAH case number for display parity, but keep the
// original around when linking.
export function displayCase(caseNo) {
  return caseNo || ''
}

export function pct(x) {
  if (x == null || isNaN(x)) return null
  return Math.round(x * 100)
}

// Outcome -> presentation tokens. Drives chip colors everywhere.
export function outcomeMeta(party) {
  switch (party) {
    case 'district':
      return { label: 'District prevailed', tone: 'district' }
    case 'respondent':
      return { label: 'Respondent prevailed', tone: 'respondent' }
    case 'mixed':
      return { label: 'Mixed', tone: 'mixed' }
    default:
      return { label: 'No ruling', tone: 'mixed' }
  }
}
