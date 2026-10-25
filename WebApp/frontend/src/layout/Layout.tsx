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
          'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
          isActive
            ? 'bg-blue-50 dark:bg-blue-600/20 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-600/30'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800',
        )
      }
    >
      {icon}
      {label}
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
        <div className="px-6 py-5 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center flex-shrink-0">
              <Crosshair size={16} className="text-white" />
            </div>
            <div>
              <div className="font-mono text-xs font-bold tracking-[0.2em] text-blue-600 dark:text-blue-400 uppercase">
                Kanat
              </div>
              <div className="font-mono text-[10px] tracking-[0.15em] text-slate-400 dark:text-slate-400 uppercase">
                Range System
              </div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
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
