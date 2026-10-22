import { Target } from 'lucide-react'
import { Group, Grouping } from '../../types'
import { mmLabel } from '../../utils/bullets'

// A Group's measure to 0.1 mm; a Group of one has no spread
const mm = (v: number | null) => (v === null ? '—' : `${v.toFixed(1)} mm`)

const MEASURES: [string, keyof Group][] = [
  ['CEP', 'cep_mm'],
  ['Mean Radius', 'mean_radius_mm'],
  ['RMS Radius', 'rms_radius_mm'],
  ['Extreme Spread', 'extreme_spread_mm'],
]

// A completed session's Groups, one row per Target, with the Bullet Holes left
// out of every Group. Nothing without a Group.
export function GroupsCard({ grouping }: { grouping: Grouping }) {
  if (grouping.groups.length === 0) return null
  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-sm dark:shadow-none mb-6">
      <div className="px-5 py-3.5 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
        <Target size={14} className="text-slate-400" />
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Groups</h2>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
            <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Target</th>
            <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Bullet Holes</th>
            <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">MPI</th>
            {MEASURES.map(([label]) => (
              <th key={label} className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {grouping.groups.map(g => (
            <tr key={g.target_index}>
              <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-400">Target {g.target_index + 1}</td>
              <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{g.n}</td>
              <td className="px-4 py-3 font-mono text-xs text-slate-500 dark:text-slate-400">
                {mmLabel({ x_mm: g.mpi_x_mm, y_mm: g.mpi_y_mm })}
              </td>
              {MEASURES.map(([label, key]) => (
                <td key={label} className="px-4 py-3 font-mono text-xs text-slate-500 dark:text-slate-400">
                  {mm(g[key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <p className="px-5 py-3 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-500">
        In no Group: Misses: {grouping.misses} · Without a Position: {grouping.without_position}
      </p>
    </div>
  )
}
