import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, Settings, VideoOff } from 'lucide-react'
import { useCameras } from '../../hooks/useCameras'
import { BulletHole, Run } from '../../types'
import { WhepPlayer } from './WhepPlayer'

// The grid for n cameras (at most 4): 1 fills the whole area, 2 stack one below
// the other, 3 make a triangle (two on top, one centred below), 4 a 2x2 square.
// More than 4 (not reachable) fall back to 3 a row.
function gridStyle(n: number): CSSProperties {
  const tracks = (count: number) => `repeat(${count}, minmax(0, 1fr))`
  if (n <= 1) return { gridTemplateColumns: '1fr', gridTemplateRows: '1fr' }
  if (n === 2) return { gridTemplateColumns: '1fr', gridTemplateRows: tracks(2) }
  if (n === 3) return { gridTemplateColumns: tracks(4), gridTemplateRows: tracks(2) }
  if (n === 4) return { gridTemplateColumns: tracks(2), gridTemplateRows: tracks(2) }
  return { gridTemplateColumns: tracks(3), gridTemplateRows: tracks(Math.ceil(n / 3)) }
}

// Only the triangle (3) needs explicit placement: the columns are quarters, so
// each video spans two — two half-width on top, one half-width centred below
const TRIANGLE_CELLS: CSSProperties[] = [
  { gridColumn: '1 / span 2', gridRow: '1' },
  { gridColumn: '3 / span 2', gridRow: '1' },
  { gridColumn: '2 / span 2', gridRow: '2' },
]

// Every enabled camera, live, sharing all of the space it is given; the
// Run's Overlay, at its latest place, with the Session's Bullet Holes, only
// over the camera it watched
export function CameraFeeds({ run, runs, bullets }: { run?: Run; runs: Run[]; bullets: BulletHole[] }) {
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

  const n = enabled.length
  return (
    <div className="grid gap-3 h-full" style={gridStyle(n)}>
      {enabled.map((camera, i) => (
        <div key={camera.id} className="min-h-0 h-full w-full" style={n === 3 ? TRIANGLE_CELLS[i] : undefined}>
          <WhepPlayer
            path={camera.alias}
            label={n > 1 ? camera.alias : undefined}
            overlay={
              run?.camera_alias === camera.alias
                ? { run, place: run.places[run.places.length - 1], bullets, runs }
                : undefined
            }
          />
        </div>
      ))}
    </div>
  )
}
