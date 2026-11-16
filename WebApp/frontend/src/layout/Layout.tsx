import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { ReactNode, useEffect } from 'react'
import { Crosshair, LayoutList, ScrollText, Settings as SettingsIcon, Sun, Moon } from 'lucide-react'
import clsx from 'clsx'
import { ErrorBoundary } from '../components/UI/ErrorBoundary'
import { useDarkMode } from '../hooks/useDarkMode'
import { log } from '../utils/logger'
import { ConnectionStatus } from './ConnectionStatus'

function NavItem({ to, icon, label, end = false }: { to: string; icon: ReactNode; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        clsx(
          'relative flex items-center gap-3 pl-4 pr-3 py-2 rounded-md text-sm font-medium transition-colors',
          isActive
            ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-800 dark:text-blue-200'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/70',
        )
      }
    >
      {({ isActive }) => (
        <>
          {/* Active items carry a signal bar at the rail, like a lit channel */}
          <span
            className={clsx(
              'absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full transition-colors',
              isActive ? 'bg-blue-600 dark:bg-blue-400' : 'bg-transparent',
            )}
          />
          {icon}
          {label}
        </>
      )}
    </NavLink>
  )
}

export function Layout() {
  const { dark, toggle } = useDarkMode()
  const { pathname } = useLocation()

  useEffect(() => {
    log.info('Page opened', { path: pathname })
  }, [pathname])

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 dark:bg-slate-950">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex flex-col">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-600 ring-1 ring-blue-700/50 flex items-center justify-center flex-shrink-0 shadow-card">
              <Crosshair size={17} className="text-white" />
            </div>
            <div>
              <div className="font-mono text-sm font-bold tracking-[0.22em] text-slate-900 dark:text-slate-100">
                KANAT
              </div>
              <div className="font-mono text-[10px] tracking-[0.14em] text-slate-400 dark:text-slate-500">
                Range System
              </div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          <NavItem to="/" icon={<LayoutList size={16} />} label="Sessions" end />
          <NavItem to="/logs" icon={<ScrollText size={16} />} label="Logs" />
          <NavItem to="/settings" icon={<SettingsIcon size={16} />} label="Settings" />
        </nav>

        <ConnectionStatus />

        {/* Footer */}
        <div className="px-4 py-4 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <p className="text-xs text-slate-400 dark:text-slate-600 font-mono">v0.1.0</p>
          <button
            onClick={toggle}
            title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            className="p-1.5 rounded-lg text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            {dark ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        {/* Keyed by page, so opening another page clears a crash */}
        <ErrorBoundary key={pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
