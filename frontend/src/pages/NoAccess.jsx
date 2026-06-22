/*
 * The access gate. Shown when no valid token is present (api.js redirects here
 * on a 401). Deliberately minimal — this is a per-person magic-link app, so the
 * remedy is "ask Nick for a link," not a login form.
 */
export default function NoAccess() {
  return (
    <div className="min-h-screen flex items-center justify-center px-6 bg-bg">
      <div className="max-w-md w-full text-center animate-fade-in-up">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent-light mb-6">
          <svg className="w-7 h-7 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>

        <h1 className="text-xl font-semibold text-text-heading mb-2">This is a private preview</h1>
        <p className="text-text-secondary leading-relaxed mb-6">
          Access to the Cert Layoff Search tool is by personal invite link. Your link may be
          missing or expired.
        </p>

        <p className="text-sm text-text-muted">
          Ask Nick for an access link, then open it again — it looks like{' '}
          <code className="px-1.5 py-0.5 rounded bg-surface border border-border-light text-text-secondary text-xs">
            …/?k=your-token
          </code>
          .
        </p>

        <p className="mt-8 text-xs text-text-muted">
          <a href="mailto:nickclair@gmail.com" className="text-accent hover:text-accent-hover">
            Request access
          </a>
        </p>
      </div>
    </div>
  )
}
