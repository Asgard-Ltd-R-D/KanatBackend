import { AlertCircle, Film, Play, RefreshCw } from 'lucide-react'
import { CameraRecording } from '../../types'
import { formatClock, formatLength } from '../../utils/format'
import { summarize } from '../../utils/recordings'

interface Props {
  recordings: CameraRecording[] | undefined
  isLoading: boolean
  isError: boolean
  onRetry: () => void
  onPlay: (alias: string) => void
}

// A completed session's recordings, one row per camera; ▶ opens the replay
export function RecordingsCard({ recordings, isLoading, isError, onRetry, onPlay }: Props) {
  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm dark:shadow-none mb-6">
      <div className="px-5 py-3.5 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
        <Film size={14} className="text-slate-400" />
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Recordings</h2>
      </div>

      {isLoading && (
        <div className="px-5 py-4">
          <div className="h-5 w-2/3 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" />
        </div>
      )}

      {isError && !recordings && (
        <div className="px-5 py-4 flex items-center gap-2 text-sm text-slate-500">
          <AlertCircle size={16} className="text-red-500 dark:text-red-400" />
          Failed to load recordings
          <button onClick={onRetry} className="ml-2 flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100">
            <RefreshCw size={12} /> Retry
          </button>
        </div>
      )}

      {recordings && recordings.length === 0 && (
        <p className="px-5 py-4 text-sm text-slate-500">No recorded video</p>
      )}

      {recordings && recordings.length > 0 && (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
          {recordings.map(r => {
            const { from, to, recordedS } = summarize(r)
            return (
              <li key={r.alias}>
                <button
                  onClick={() => onPlay(r.alias)}
                  className="group w-full px-5 py-3 flex items-center gap-4 text-left hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                >
                  <span className="w-7 h-7 rounded-md border border-slate-200 dark:border-slate-700 flex items-center justify-center shrink-0 text-slate-500 dark:text-slate-400 group-hover:text-blue-600 dark:group-hover:text-blue-400 group-hover:border-blue-300 dark:group-hover:border-blue-500/50 transition-colors">
                    <Play size={12} />
                  </span>
                  <span className="w-32 font-mono text-sm text-slate-800 dark:text-slate-200 truncate">{r.alias}</span>
                  <span className="font-mono text-xs text-slate-500 dark:text-slate-400">
                    {formatClock(from)} – {formatClock(to)}
                  </span>
                  <span className="ml-auto flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
                    <span className="font-mono">{formatLength(recordedS)} recorded</span>
                    {r.spans.length > 1 && <span>{r.spans.length} parts</span>}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
