import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { bootstrapToken, getMe, track } from '../lib/api'

/*
 * App chrome: header with brand + nav, content outlet.
 * Also the single place that bootstraps the access token (reads ?k=, persists)
 * and confirms it via /api/me. An invalid/missing token routes to NoAccess.
 * Fires a page_view event on every route change.
 */
export default function Layout() {
  const location = useLocation()
  const [me, setMe] = useState(null)

  // Token bootstrap + identity check, once on mount.
  useEffect(() => {
    bootstrapToken()
    const controller = new AbortController()
    getMe(controller.signal)
      .then((data) => setMe(data?.name || null))
      .catch((err) => {
        // 401 already redirects inside api.js; swallow others (backend warming up).
        if (err?.status !== 401) setMe(null)
      })
    return () => controller.abort()
  }, [])

  // page_view on every navigation.
  useEffect(() => {
    track('page_view', {
      target_id: location.pathname,
      filters: { search: location.search || null },
    })
  }, [location.pathname, location.search])

  return (
    <div className="min-h-screen flex flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-2 focus:left-2 focus:px-4 focus:py-2 focus:bg-accent focus:text-white focus:rounded-lg focus:text-sm focus:font-medium"
      >
        Skip to content
      </a>

      <header className="border-b border-border bg-surface/85 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 md:px-8 py-3.5 flex items-center gap-6">
          <Link to="/" className="flex items-baseline gap-2 no-underline group">
            <span className="text-[1.05rem] font-semibold tracking-tight text-text-heading group-hover:text-accent transition-colors">
              Cert Layoff
            </span>
            <span className="text-[1.05rem] font-normal text-text-secondary">Search</span>
          </Link>

          <nav className="flex items-center gap-1 text-sm">
            <HeaderLink to="/">Search</HeaderLink>
            <HeaderLink to="/alj">ALJ Profiles</HeaderLink>
            <HeaderLink to="/reports">Reports</HeaderLink>
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <span className="hidden md:inline text-xs text-text-muted">
              California OAH certificated-layoff decisions
            </span>
            {me && (
              <span
                className="inline-flex items-center gap-1.5 text-xs font-medium text-text-secondary bg-surface-soft border border-border-light rounded-full pl-2 pr-2.5 py-1"
                title={`Signed in as ${me}`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                {me}
              </span>
            )}
          </div>
        </div>
      </header>

      <main id="main" className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 md:px-8 py-8 md:py-10">
        <Outlet />
      </main>

      <footer className="border-t border-border-light mt-8">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 md:px-8 py-5 text-xs text-text-muted flex flex-wrap items-center gap-x-4 gap-y-1">
          <span>Every holding is traceable to a real OAH decision.</span>
          <span className="text-text-muted/70">No generative answers — structured signal only.</span>
        </div>
      </footer>
    </div>
  )
}

function HeaderLink({ to, children }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        [
          'px-3 py-1.5 rounded-md no-underline transition-colors',
          isActive
            ? 'text-accent font-medium bg-accent-light'
            : 'text-text-secondary hover:text-text-primary hover:bg-surface-soft',
        ].join(' ')
      }
    >
      {children}
    </NavLink>
  )
}
