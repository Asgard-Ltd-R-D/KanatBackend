import { useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, Maximize2, Minimize2, Settings, VideoOff } from 'lucide-react'
import clsx from 'clsx'
import { useCameras } from '../../hooks/useCameras'
import { BoardDetection, BulletHole, Camera, Run } from '../../types'
import { DetectionBadge } from '../Session/DetectionBadge'
import { WhepPlayer } from './WhepPlayer'

// The grid for n cameras (at most 4): 1 fills the whole area, 2 sit side by
// side, 3 make a triangle (two on top, one centred below), 4 a 2x2 square.
// More than 4 (not reachable) fall back to 3 a row.
function gridStyle(n: number): CSSProperties {
  const tracks = (count: number) => `repeat(${count}, minmax(0, 1fr))`
  if (n <= 1) return { gridTemplateColumns: '1fr', gridTemplateRows: '1fr' }
  if (n === 2) return { gridTemplateColumns: tracks(2), gridTemplateRows: '1fr' }
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

// Every enabled camera (board), live, sharing all of the space it is given. Each
// tile draws its OWN Overlay from that board's latest Run and Bullet Holes, at
// its latest place, only while that board's Run watches (matched by camera_alias).
export function CameraFeeds({ runs, bullets, detections }: { runs: Run[]; bullets: BulletHole[]; detections: BoardDetection[] }) {
  const { data: cameras, isLoading, isError } = useCameras()
  const enabled = cameras?.filter(c => c.enabled) ?? []
  // The camera shown big; the others shrink to a strip. null is the equal grid.
  const [focused, setFocused] = useState<string | null>(null)

  // One board's tile: name + detection status above, the stream below, and a
  // button to focus it (big) or, when it is the focused one, restore the grid.
  const tile = (camera: Camera, opts: { compact?: boolean; cell?: CSSProperties } = {}) => {
    const { compact = false, cell } = opts
    const isFocused = focused === camera.alias
    const boardRuns = runs.filter(r => r.camera_alias === camera.alias)
    const run = boardRuns[boardRuns.length - 1]
    const detection = detections.find(d => d.camera_alias === camera.alias)?.detection
    const watches = detection?.state === 'watching' || detection?.state === 'ending'
    const boardBullets = bullets.filter(b => b.camera_alias === camera.alias)
    return (
      <div key={camera.id} className={clsx('min-h-0 w-full flex flex-col', !compact && 'h-full')} style={cell}>
        <div className="flex items-center gap-1.5 mb-1.5 min-h-[20px]">
          <span className={clsx('font-medium text-slate-500 dark:text-slate-400', compact ? 'text-[11px]' : 'text-xs')}>
            {camera.alias}
          </span>
          {!compact && detection && <DetectionBadge detection={detection} />}
        </div>
        {/* Compact thumbnails keep a 16:9 shape so the video never looks smashed */}
        <div className={clsx(compact ? 'aspect-video w-full' : 'flex-1 min-h-0')}>
          <WhepPlayer
            path={camera.alias}
            overlay={
              watches && run
                ? { run, place: run.places[run.places.length - 1], bullets: boardBullets, runs: boardRuns }
                : undefined
            }
            action={
              <button
                type="button"
                onClick={() => setFocused(isFocused ? null : camera.alias)}
                title={isFocused ? 'Restore grid' : 'Focus this camera'}
                className="flex items-center justify-center rounded-full p-1.5 bg-black/55 hover:bg-black/75 text-white/80 backdrop-blur-sm transition-colors"
              >
                {isFocused ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              </button>
            }
          />
        </div>
      </div>
    )
  }

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
  const focusedCamera = focused ? enabled.find(c => c.alias === focused) : undefined

  // Spotlight: the focused camera big on the left, the rest as small 16:9
  // thumbnails in a column on the right. Each thumbnail's focus button takes
  // the big slot; the focused one's button restores the grid. Only when >1 camera.
  if (focusedCamera && n > 1) {
    const others = enabled.filter(c => c.alias !== focusedCamera.alias)
    return (
      <div className="flex gap-3 h-full">
        <div className="flex-1 min-w-0">{tile(focusedCamera)}</div>
        <div className="w-60 shrink-0 flex flex-col gap-3 overflow-y-auto">
          {others.map(camera => (
            <div key={camera.id} className="shrink-0">{tile(camera, { compact: true })}</div>
          ))}
        </div>
      </div>
    )
  }

  // Equal grid
  return (
    <div className="grid gap-3 h-full" style={gridStyle(n)}>
      {enabled.map((camera, i) => tile(camera, { cell: n === 3 ? TRIANGLE_CELLS[i] : undefined }))}
    </div>
  )
}
