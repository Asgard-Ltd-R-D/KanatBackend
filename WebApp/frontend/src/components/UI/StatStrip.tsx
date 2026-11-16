import { ReactNode } from 'react'
import clsx from 'clsx'

export interface Stat {
  label: string
  value: ReactNode
}

// A row of readouts — label over value, hairline-separated — anchored as one
// panel rather than floating cards. The same instrument strip the range report
// (PDF) opens with, so the app and its exports read as one system.
export function StatStrip({ items, className }: { items: Stat[]; className?: string }) {
  return (
    <div
      className={clsx(
        'flex rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-card dark:shadow-none overflow-hidden',
        className,
      )}
    >
      {items.map((it, i) => (
        <div key={i} className={clsx('flex-1 px-5 py-3.5', i > 0 && 'border-l border-slate-200 dark:border-slate-800')}>
          <div className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1">{it.label}</div>
          <div className="text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-100 tnum">{it.value}</div>
        </div>
      ))}
    </div>
  )
}
