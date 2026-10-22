import { Link } from 'react-router-dom'
import { AlertCircle, Settings, VideoOff } from 'lucide-react'
import { useCameras } from '../../hooks/useCameras'
import { BulletHole, Run } from '../../types'
import { WhepPlayer } from './WhepPlayer'

// Columns and rows for n cameras: 1 fills the area, 2 stack, 3-4 make a 2x2
// grid, more go 3 to a row
function gridFor(n: number): { columns: number; rows: number } {
  if (n <= 1) return { columns: 1, rows: 1 }
  if (n === 2) return { columns: 1, rows: 2 }
  if (n <= 4) return { columns: 2, rows: 2 }
  return { columns: 3, rows: Math.ceil(n / 3) }
}

// Every enabled camera, live, sharing all of the space it is given; the
// Run's Overlay, with the Session's Bullet Holes, only over the camera it watched
export function CameraFeeds({ run, bullets }: { run?: Run; bullets: BulletHole[] }) {
  const { data: cameras, isLoading, isError } = useCameras()
  const enabled = cameras?.filter(c => c.enabled) ?? []

  if (isLoading) {
    return <div className="h-full bg-slate-200 dark:bg-slate-800 rounded-xl animate-pulse" />
  }

  // Not "no cameras": the list could not be loaded, and is being tried again
  if (isError && !cameras) {
    return (
      <div className="h-full bg-white dark:bg-slate-900 border border-dashed border-slate-300 dark:border-slate-700 rounded-xl flex flex-col items-center justify-center gap-2">
        <AlertCircle size={28} className="text-red-500 dark:text-red-400" />
        <p className="text-slate-500 text-sm">Failed to load cameras</p>
        <p className="text-slate-400 dark:text-slate-600 text-xs">Retrying…</p>
      </div>
    )
  }

  if (enabled.length === 0) {
    return (
      <div className="h-full bg-white dark:bg-slate-900 border border-dashed border-slate-300 dark:border-slate-700 rounded-xl flex flex-col items-center justify-center gap-3">
        <VideoOff size={28} className="text-slate-300 dark:text-slate-700" />
        <p className="text-slate-500 text-sm">No cameras configured</p>
        <Link
          to="/settings"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-medium transition-colors"
        >
          <Settings size={14} /> Go to Settings
        </Link>
      </div>
    )
  }

  const { columns, rows } = gridFor(enabled.length)
  return (
    <div
      className="grid gap-3 h-full"
      style={{
        gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
        gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
      }}
    >
      {enabled.map(camera => (
        <WhepPlayer
          key={camera.id}
          path={camera.alias}
          label={enabled.length > 1 ? camera.alias : undefined}
          overlay={run?.camera_alias === camera.alias ? { view: run.baseline_view, bullets } : undefined}
        />
      ))}
    </div>
  )
}
