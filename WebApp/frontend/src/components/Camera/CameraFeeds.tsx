import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, Maximize2, Minimize2, Settings, VideoOff } from 'lucide-react'
import clsx from 'clsx'
import { useCameras } from '../../hooks/useCameras'
import { uploadBaselineImage } from '../../api/baselineImage'
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
export function CameraFeeds({ sessionId, runs, bullets, detections }: { sessionId: string; runs: Run[]; bullets: BulletHole[]; detections: BoardDetection[] }) {
  const { data: cameras, isLoading, isError } = useCameras()
  const enabled = cameras?.filter(c => c.enabled) ?? []
  // The camera shown big; the others shrink to a strip. null is the equal grid.
  const [focused, setFocused] = useState<string | null>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  // (alias, Run taken_at) pairs whose baseline frame was already grabbed, so a
  // Run is captured once and a retake (new taken_at) captures again
  const captured = useRef(new Set<string>())

  // When a board's latest Run first watches (its baseline is established), grab
  // one clean frame from its <video> (no overlay) and upload it. Best-effort.
  useEffect(() => {
    for (const d of detections) {
      if (d.detection?.state !== 'watching') continue
      const alias = d.camera_alias
      const boardRuns = runs.filter(r => r.camera_alias === alias)
      const run = boardRuns[boardRuns.length - 1]
      if (!run) continue
      const key = `${alias}\u0000${run.taken_at}`
      if (captured.current.has(key)) continue
      const video = gridRef.current?.querySelector<HTMLVideoElement>(`[data-camera="${CSS.escape(alias)}"] video`)
      // No decoded frame yet: leave it unmarked so the next update retries
      if (!video || video.videoWidth === 0 || video.videoHeight === 0) continue
      captured.current.add(key)
      try {
        const canvas = document.createElement('canvas')
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        canvas.getContext('2d')!.drawImage(video, 0, 0, canvas.width, canvas.height)
        canvas.toBlob(blob => {
          if (!blob) return
          uploadBaselineImage(sessionId, alias, blob).catch(err => console.warn('baseline image upload failed', err))
        }, 'image/png')
      } catch (err) {
        console.warn('baseline frame capture failed', err)
      }
    }
  }, [sessionId, runs, detections])

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
      <div key={camera.id} data-camera={camera.alias} className={clsx('min-h-0 w-full flex flex-col', !compact && 'h-full')} style={cell}>
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
  // Spotlight only makes sense with more than one camera
  const spotlight = focused != null && n > 1
  const others = spotlight ? enabled.filter(c => c.alias !== focused) : []

  // One grid holds every tile in a fixed order, so changing focus only re-styles
  // cells — React keeps each WhepPlayer mounted and the live video never drops.
  // Spotlight: the focused camera fills the left column, the rest stack in a
  // narrow right column; otherwise the equal grid for n cameras.
  const containerStyle: CSSProperties = spotlight
    ? { gridTemplateColumns: '1fr 15rem', gridTemplateRows: `repeat(${others.length}, minmax(0, 1fr))` }
    : gridStyle(n)

  const cellOf = (camera: Camera, i: number): CSSProperties | undefined => {
    if (spotlight) {
      return camera.alias === focused
        ? { gridColumn: '1', gridRow: '1 / -1' }
        : { gridColumn: '2', gridRow: `${others.findIndex(c => c.id === camera.id) + 1}` }
    }
    return n === 3 ? TRIANGLE_CELLS[i] : undefined
  }

  return (
    <div ref={gridRef} className="grid gap-3 h-full min-h-0" style={containerStyle}>
      {enabled.map((camera, i) => tile(camera, { compact: spotlight && camera.alias !== focused, cell: cellOf(camera, i) }))}
    </div>
  )
}
