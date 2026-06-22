import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import DecisionReader from '../components/DecisionReader'
import { getDecision, track } from '../lib/api'

/*
 * The in-app reader route. Fetches the served record by case number and renders
 * it via DecisionReader. Tracks dwell time (open -> unmount) so we know how long
 * an attorney spent on a decision.
 */
export default function DecisionPage() {
  const { caseNo } = useParams()
  const navigate = useNavigate()
  const [record, setRecord] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState(false)
  const enteredAt = useRef(Date.now())

  useEffect(() => {
    enteredAt.current = Date.now()
    setLoading(true)
    setNotFound(false)
    setError(false)
    const c = new AbortController()

    getDecision(caseNo, c.signal)
      .then((data) => {
        setRecord(data)
        setLoading(false)
      })
      .catch((err) => {
        if (err.name === 'AbortError' || err.status === 401) return
        if (err.status === 404) setNotFound(true)
        else setError(true)
        setLoading(false)
      })

    window.scrollTo(0, 0)

    // On leave: log dwell time on this decision.
    return () => {
      c.abort()
      const dwell = Date.now() - enteredAt.current
      if (dwell > 800) {
        track('open_decision', { target_id: caseNo, dwell_ms: dwell })
      }
    }
  }, [caseNo])

  return (
    <div>
      <button
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-1 text-sm font-medium text-text-secondary hover:text-accent mb-6"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15 19l-7-7 7-7" />
        </svg>
        Back to results
      </button>

      {loading ? (
        <DecisionSkeleton />
      ) : notFound ? (
        <Message
          title="Decision not found"
          body={`No decision matches “${caseNo}”. It may have been removed or the link is mistyped.`}
        />
      ) : error ? (
        <Message title="Couldn’t load this decision" body="An unexpected error occurred. Please try again shortly." />
      ) : (
        <DecisionReader record={record} />
      )}
    </div>
  )
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

function DecisionSkeleton() {
  return (
    <div aria-hidden="true" className="animate-pulse">
      <div className="h-6 w-32 bg-border-light rounded mb-4" />
      <div className="h-8 w-2/3 bg-border-light rounded mb-3" />
      <div className="h-4 w-1/2 bg-border-light rounded mb-8" />
      <div className="h-32 w-full bg-border-light rounded mb-6" />
      <div className="h-64 w-full bg-border-light rounded" />
    </div>
  )
}
