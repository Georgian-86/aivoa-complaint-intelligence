import { useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Icon, type IconName } from './Icon'
import { useAppDispatch, useAppSelector } from '@/app/store'
import { railToggled, themeToggled, toastDismissed } from '@/features/system/systemSlice'
import './AppShell.css'

const NAV: { to: string; label: string; icon: IconName; group: string }[] = [
  { to: '/intake', label: 'Log Complaint', icon: 'intake', group: 'Intake' },
  { to: '/register', label: 'Complaint Register', icon: 'register', group: 'Quality Records' },
  { to: '/dashboard', label: 'Trend Dashboard', icon: 'dashboard', group: 'Quality Records' },
]

const TITLES: Record<string, [string, string]> = {
  '/intake': ['Customer Complaint', 'Log new complaint'],
  '/register': ['Quality Records', 'Complaint register'],
  '/dashboard': ['Quality Records', 'Trend dashboard'],
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const dispatch = useAppDispatch()
  const { railCollapsed, theme, pipeline, status, toast } = useAppSelector((s) => s.system)
  const total = useAppSelector((s) => s.complaints.total)
  const { pathname } = useLocation()

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => dispatch(toastDismissed()), 5200)
    return () => clearTimeout(timer)
  }, [toast, dispatch])

  const crumbKey = Object.keys(TITLES).find((k) => pathname.startsWith(k)) ?? '/intake'
  const [section, page] = TITLES[crumbKey]
  const groups = [...new Set(NAV.map((n) => n.group))]
  const llmOn = pipeline?.llm_configured ?? false

  return (
    <div className="shell">
      <aside className={`rail${railCollapsed ? ' is-collapsed' : ''}`}>
        <div className="rail-brand">
          <img className="rail-mark" src="/mark.svg" alt="" />
          {!railCollapsed && (
            <div className="rail-name">
              <b>Complaint Intelligence</b>
              <span>AIVOA · QMS</span>
            </div>
          )}
        </div>

        <nav className="rail-nav">
          {groups.map((group) => (
            <div key={group}>
              {!railCollapsed && <div className="rail-section">{group}</div>}
              {NAV.filter((n) => n.group === group).map((item) => (
                <NavLink
                  key={item.to} to={item.to} title={item.label}
                  className={({ isActive }) => `rail-link${isActive ? ' is-active' : ''}`}
                >
                  <Icon name={item.icon} size={17} />
                  {!railCollapsed && (
                    <>
                      <span className="grow truncate">{item.label}</span>
                      {item.to === '/register' && total > 0 && (
                        <span className="rail-count">{total}</span>
                      )}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="rail-foot">
          <div className={`rail-engine${llmOn ? '' : ' is-offline'}`}>
            <span className="pulse" />
            {!railCollapsed && (
              <div className="grow" style={{ minWidth: 0 }}>
                <b>{llmOn ? 'Groq inference live' : 'Deterministic mode'}</b>
                <span className="truncate">
                  {llmOn ? pipeline?.models.extraction ?? '—' : 'no GROQ_API_KEY'}
                </span>
              </div>
            )}
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button
            className="btn btn-ghost btn-icon" onClick={() => dispatch(railToggled())}
            aria-label={railCollapsed ? 'Expand navigation' : 'Collapse navigation'}
          >
            <Icon name="chevron" size={15}
              style={{ transform: railCollapsed ? 'none' : 'rotate(180deg)' }} />
          </button>

          <div className="crumbs grow">
            <span>{section}</span>
            <span className="sep">/</span>
            <b>{page}</b>
          </div>

          <span className="env-badge" title="Deployment environment">
            <Icon name="flask" size={11} /> Validation
          </span>
          {status === 'offline' && (
            <span className="chip chip-critical"><span className="dot" /> API offline</span>
          )}
          <button
            className="btn btn-ghost btn-icon" onClick={() => dispatch(themeToggled())}
            aria-label="Toggle colour theme" title="Toggle colour theme"
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={15} />
          </button>
        </header>

        <main className="page">
          <div className="page-inner">{children}</div>
        </main>
      </div>

      {toast && (
        <div className={`toast${toast.tone === 'ok' ? '' : ` is-${toast.tone}`}`} role="status">
          <Icon name={toast.tone === 'ok' ? 'check' : 'alert'} size={15}
            style={{ marginTop: 1, color: toast.tone === 'error' ? 'var(--critical)' : 'var(--accent)' }} />
          <div className="grow t-sm">{toast.message}</div>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={() => dispatch(toastDismissed())}>
            <Icon name="close" size={12} />
          </button>
        </div>
      )}
    </div>
  )
}
