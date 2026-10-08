import { NavLink, Outlet } from 'react-router-dom'
import { Crosshair, LayoutList } from 'lucide-react'
import clsx from 'clsx'

export function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-[#020617]">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col">
        {/* Logo */}
        <div className="px-6 py-5 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center flex-shrink-0">
              <Crosshair size={16} className="text-white" />
            </div>
            <div>
              <div className="font-mono text-xs font-bold tracking-[0.2em] text-blue-400 uppercase">
                Kanat
              </div>
              <div className="font-mono text-[10px] tracking-[0.15em] text-slate-500 uppercase">
                Range System
              </div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-600/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800',
              )
            }
          >
            <LayoutList size={16} />
            Sessions
          </NavLink>
        </nav>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-800">
          <p className="text-xs text-slate-600 font-mono">v0.1.0</p>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
