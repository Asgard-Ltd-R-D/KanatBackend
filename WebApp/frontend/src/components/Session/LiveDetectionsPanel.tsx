import { Crosshair } from 'lucide-react'
import { BulletHole } from '../../types'
import { formatClock } from '../../utils/format'
import { SourceBadge } from './SourceBadge'

// An active session's Bullet Holes as they arrive, newest first
export function LiveDetectionsPanel({ bullets }: { bullets: BulletHole[] }) {
  return (
    <div className="flex-1 min-h-[300px] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-sm dark:shadow-none flex flex-col">
      {/* Panel header */}
      <div className="shrink-0 px-4 py-2.5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-400">
          Newest first
        </span>
        <span className="text-[10px] tabular-nums text-slate-400 dark:text-slate-400">
          {bullets.length} detected
        </span>
      </div>

      {/* Scrollable list or empty state */}
      {bullets.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          <Crosshair size={28} className="text-slate-300 dark:text-slate-700" />
          <p className="text-slate-400 dark:text-slate-600 text-sm">Waiting for detections…</p>
        </div>
      ) : (
        <ul className="flex-1 min-h-0 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/60">
          {[...bullets].reverse().map(b => (
            <li key={b.id} className="px-4 py-2.5 flex items-start gap-3">
              <span className="text-[10px] font-mono text-slate-400 dark:text-slate-600 w-5 shrink-0 pt-0.5 text-right">
                {b.rank}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <SourceBadge source={b.source} />
                </div>
                <p className="text-[10px] font-mono text-slate-400 dark:text-slate-600">
                  {formatClock(b.first_seen_at)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
