import { Crosshair, Trash2 } from 'lucide-react'
import { BulletHole } from '../../types'
import { formatClock } from '../../utils/format'
import { byTarget, cmLabel } from '../../utils/bullets'
import { SourceBadge } from './SourceBadge'

interface Props {
  bullets: BulletHole[]
  onDelete: (bullet: BulletHole) => void
}

// A completed session's Bullet Holes, one section per Target (ranks as
// numbered across the board), each one deletable. Positions in cm from the
// Target's centre.
export function BulletLog({ bullets, onDelete }: Props) {
  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-sm dark:shadow-none">
      <div className="px-5 py-3.5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
          Bullet Log
          <span className="ml-2 text-xs font-normal text-slate-400 dark:text-slate-400">({bullets.length})</span>
        </h2>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
            <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider w-12">#</th>
            <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Detected At</th>
            <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Position (cm)</th>
            <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Source</th>
            <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {bullets.length === 0 && (
            <tr>
              <td colSpan={5} className="py-16 text-center">
                <div className="flex flex-col items-center gap-3">
                  <Crosshair size={32} className="text-slate-300 dark:text-slate-700" />
                  <p className="text-slate-500 dark:text-slate-400 text-sm">No bullets recorded</p>
                </div>
              </td>
            </tr>
          )}
          {byTarget(bullets).map(section => [
            <tr key={`section-${section.label}`} className="bg-slate-50/70 dark:bg-slate-800/30">
              <td colSpan={5} className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300">
                {section.label}
                <span className="ml-1.5 font-normal text-slate-400">({section.bullets.length})</span>
              </td>
            </tr>,
            ...section.bullets.map(b => (
            <tr key={b.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
              <td className="px-4 py-3 text-slate-400 dark:text-slate-600 font-mono text-xs">{b.rank}</td>
              <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">
                {formatClock(b.first_seen_at)}
              </td>
              <td className="px-4 py-3 font-mono text-xs text-slate-500 dark:text-slate-400">
                {cmLabel(b)}
              </td>
              <td className="px-4 py-3"><SourceBadge source={b.source} /></td>
              <td className="px-4 py-3">
                <div className="flex justify-end">
                  <button
                    onClick={() => onDelete(b)}
                    className="p-1.5 text-slate-400 dark:text-slate-600 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-400/10 rounded transition-colors"
                    title="Delete bullet"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </td>
            </tr>
            )),
          ])}
        </tbody>
      </table>
    </div>
  )
}
