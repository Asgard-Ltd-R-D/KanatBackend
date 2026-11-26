import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X, Undo2 } from 'lucide-react'
import { createBullet } from '../../api/bullets'
import { BulletHole, Run } from '../../types'
import { getBaselineImage } from '../../api/baselineImage'
import { holesOver, project, type Point as Pt } from '../../utils/overlay'
import { millimetres, pixelToTemplate, targetOfPoint } from '../../utils/targets'
import targetImg from '../../assets/target.png'

// The target artwork is authored at this pixel size, and a Bullet Hole's
// position is stored in these same template coordinates. So a click on the
// image maps straight to a position: no calibration, no homography.
const TEMPLATE_W = 1405
const TEMPLATE_H = 1120

// A placed shot: its template position plus a stable idempotency key, fixed when
// placed so a retry of a partly-failed batch does not duplicate it. Placed on the
// real frame, it also carries its target and millimetres from that target's centre.
type Point = { x: number; y: number; key: string; target_index?: number; x_mm?: number; y_mm?: number }

// Same style as the live overlay (Camera/Overlay.tsx): a hollow ring, number above
const OUTLINE_COLOUR = '#22d3ee'
const SHEET_COLOUR = '#fbbf24'
const MANUAL_COLOUR = '#fbbf24'
const textOutline = { stroke: 'black', strokeWidth: 3, paintOrder: 'stroke' } as const

interface Props {
  open: boolean
  sessionId: string
  camera: string | null // the board (camera alias) the hole is added to; null for no board
  context?: BulletHole[] // the board's existing holes, drawn for reference
  runs?: Run[] // the board's Runs (taken_at order), to place the existing holes right
  onClose: () => void
  onSuccess: () => void
}

export function AddBulletModal({ open, sessionId, camera, context = [], runs = [], onClose, onSuccess }: Props) {
  const qc = useQueryClient()
  // The points placed so far, in template coordinates, in the order clicked
  const [points, setPoints] = useState<Point[]>([])
  const [notice, setNotice] = useState<string | null>(null)

  // The latest Run's view says whether the real frame can be used at all: only
  // with sheets, ring centres and a print scale. Without them the artwork is
  // all there is, so the frame is not even fetched.
  const latestRun = runs[runs.length - 1]
  const view = latestRun?.baseline_view
  const hasGeometry = !!(
    view && view.sheets && view.sheets.length > 0 && view.ring_centres &&
    view.ring_centres.length >= view.sheets.length && typeof view.mm_per_px === 'number'
  )

  // The board's real baseline frame, when one was captured (null on 404)
  const frame = useQuery({
    queryKey: ['baseline-image', sessionId, camera],
    queryFn: () => getBaselineImage(sessionId, camera as string),
    enabled: open && camera !== null && hasGeometry,
    retry: false,
    staleTime: Infinity,
  })
  const frameBlob = frame.data ?? null
  const [frameUrl, setFrameUrl] = useState<string | null>(null)
  useEffect(() => {
    // Also released while the modal is closed (the blob stays cached)
    if (!frameBlob || !open) {
      setFrameUrl(null)
      return
    }
    const url = URL.createObjectURL(frameBlob)
    setFrameUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [frameBlob, open])

  const mutation = useMutation({
    // Add every placed point in one go. Sent one after another (not in parallel)
    // so the board's ranks come out in the order they were clicked. Each carries
    // its own idempotency key, so if the batch fails partway and the operator
    // adds again, the shots already saved return as themselves, not duplicates.
    mutationFn: async (pts: Point[]) => {
      for (const p of pts) {
        await createBullet(sessionId, {
          version: 'v2',
          // The moment the user adds them, not a date they pick
          first_seen_at: new Date().toISOString(),
          position: { x: p.x, y: p.y },
          ...(p.target_index !== undefined ? { target_index: p.target_index, x_mm: p.x_mm, y_mm: p.y_mm } : {}),
          camera,
          source: 'manual',
          idempotency_key: p.key,
        })
      }
    },
    // On success or partial failure alike, so shots already saved show up
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['session', sessionId] })
      qc.invalidateQueries({ queryKey: ['sessions'] })
    },
    onSuccess: () => {
      onSuccess()
      // Close directly, not through close(): React Query runs onSuccess while the
      // mutation still reads pending, so close()'s pending guard would keep the
      // modal open. This is the successful completion, so dismiss it.
      setPoints([])
      onClose()
    },
  })

  function close() {
    // Don't dismiss while a batch is in flight: reset() would clear isPending
    // without cancelling the requests still to run. It auto-closes on success.
    if (mutation.isPending) return
    setPoints([])
    setNotice(null)
    mutation.reset()
    onClose()
  }

  // Turn a click into template coordinates. On the real frame the click is a
  // picture pixel: map it back to the template, find the A4 sheet it lands in
  // (its target) and measure millimetres from that target's centre. On the
  // artwork the image is the template 1:1, with no attribution.
  function handleClick(e: React.MouseEvent<SVGSVGElement>) {
    if (mutation.isPending || !space) return
    const rect = e.currentTarget.getBoundingClientRect()
    const sx = ((e.clientX - rect.left) / rect.width) * space.width
    const sy = ((e.clientY - rect.top) / rect.height) * space.height
    const round = (v: number) => Math.round(v * 10) / 10
    if (!geometry) {
      setNotice(null)
      setPoints(ps => [...ps, { x: round(sx), y: round(sy), key: crypto.randomUUID() }])
      return
    }
    const t = pixelToTemplate(geometry.H, [sx, sy])
    const target = targetOfPoint(geometry.sheets, t)
    if (target === null) {
      setNotice('That spot is outside every target sheet. Click inside a target\'s A4 sheet.')
      return
    }
    setNotice(null)
    const { x_mm, y_mm } = millimetres(geometry.ringCentres[target], geometry.mmPerPx, t)
    setPoints(ps => [...ps, { x: round(t[0]), y: round(t[1]), key: crypto.randomUUID(), target_index: target, x_mm, y_mm }])
  }

  function removeAt(i: number) {
    if (mutation.isPending) return
    setPoints(ps => ps.filter((_, idx) => idx !== i))
  }

  if (!open) return null

  const count = points.length
  // Existing holes may span several Runs in different template spaces (a retake
  // starts a new Run, ADR-0009). Carry them into the latest Run's space — the one
  // the artwork stands for — the same way the live overlay does, so the reference
  // dots sit where the holes really are. No Runs (manual-only board): drawn as-is.
  const contextPoints = latestRun
    ? holesOver(latestRun, runs, context)
    : context.map(b => [b.position_x, b.position_y] as [number, number])

  // The real frame is used only with a captured frame and a Baseline View that
  // resolved sheets, ring centres and a print scale; otherwise the artwork, as before
  const geometry =
    frameUrl && hasGeometry && view && view.sheets && view.ring_centres && typeof view.mm_per_px === 'number'
      ? { H: view.template_to_picture, sheets: view.sheets, ringCentres: view.ring_centres, mmPerPx: view.mm_per_px, view }
      : null
  // Frame still loading: wait, rather than flash the artwork then swap it
  // (also the render between the blob arriving and its URL being made)
  const waiting = camera !== null && hasGeometry && (frame.isLoading || (frameBlob !== null && !frameUrl))
  const space = waiting
    ? null
    : geometry
      ? { width: geometry.view.picture.width, height: geometry.view.picture.height }
      : { width: TEMPLATE_W, height: TEMPLATE_H }
  // Template point -> the drawing's space (frame px, or the template itself)
  const toSpace = (p: Pt): Pt => (geometry ? project(geometry.H, p) : p)
  const unit = space ? space.width / 600 : 1 // 1 screen-ish px at a ~600px display
  const RING = 9 * unit

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/30 dark:bg-black/60 backdrop-blur-sm" onClick={close} />
      <div className="relative bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-2xl w-full max-w-xl p-6 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Add Bullets{camera ? ` · ${camera}` : ''}
          </h3>
          <button onClick={close} disabled={mutation.isPending} className="text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
            <X size={20} />
          </button>
        </div>

        <div className="relative select-none rounded-lg overflow-hidden border border-slate-200 dark:border-slate-800">
          {space ? (
            <>
              <img
                src={geometry ? (frameUrl as string) : targetImg}
                alt={geometry ? 'Baseline frame' : 'Target'}
                width={space.width}
                height={space.height}
                draggable={false}
                style={{ aspectRatio: `${space.width} / ${space.height}` }}
                className="block w-full h-auto"
              />
              <svg
                viewBox={`0 0 ${space.width} ${space.height}`}
                onClick={handleClick}
                className="absolute inset-0 w-full h-full cursor-crosshair"
              >
                {/* Valid zones: each target's A4 sheet and outline */}
                {geometry?.sheets.map(([a, b], i) => {
                  const corners = [a, [b[0], a[1]], b, [a[0], b[1]]] as Pt[]
                  return (
                    <polygon
                      key={`sheet-${i}`}
                      points={corners.map(c => toSpace(c).join(',')).join(' ')}
                      fill="rgba(251,191,36,0.08)"
                      stroke={SHEET_COLOUR}
                      strokeWidth={1.5 * unit}
                      strokeDasharray={`${6 * unit} ${4 * unit}`}
                      pointerEvents="none"
                    />
                  )
                })}
                {geometry?.view.targets.map((outline, i) => (
                  <polygon
                    key={`outline-${i}`}
                    points={outline.map(c => toSpace(c).join(',')).join(' ')}
                    fill="none"
                    stroke={OUTLINE_COLOUR}
                    strokeWidth={2 * unit}
                    strokeLinejoin="round"
                    pointerEvents="none"
                  />
                ))}

                {/* Existing holes, faint, for context */}
                {context.map((b, i) => {
                  const [x, y] = toSpace(contextPoints[i])
                  return (
                    <circle key={b.id} cx={x} cy={y} r={4 * unit} fill="black" fillOpacity={0.7} pointerEvents="none">
                      <title>{`#${b.rank}`}</title>
                    </circle>
                  )
                })}

                {/* The shots being placed, as the live overlay draws a hole: a
                    hollow ring with its number above; click one to remove it */}
                {points.map((p, i) => {
                  const [x, y] = toSpace([p.x, p.y])
                  return (
                    <g
                      key={p.key}
                      className="cursor-pointer"
                      onClick={e => {
                        e.stopPropagation()
                        removeAt(i)
                      }}
                    >
                      <title>Remove this shot</title>
                      <circle cx={x} cy={y} r={RING} fill="none" stroke={MANUAL_COLOUR} strokeWidth={2 * unit} />
                      <circle cx={x} cy={y} r={RING + 4 * unit} fill="transparent" />
                      <text
                        x={x}
                        y={y - RING - 3 * unit}
                        textAnchor="middle"
                        fontSize={12 * unit}
                        fontWeight={700}
                        fill={MANUAL_COLOUR}
                        {...textOutline}
                        strokeWidth={3 * unit}
                      >
                        {i + 1}
                      </text>
                    </g>
                  )
                })}
              </svg>
            </>
          ) : (
            <div className="flex items-center justify-center text-sm text-slate-500 dark:text-slate-400" style={{ aspectRatio: `${TEMPLATE_W} / ${TEMPLATE_H}` }}>
              Loading frame…
            </div>
          )}
        </div>

        {notice && <p className="text-amber-600 dark:text-amber-400 text-xs mt-2">{notice}</p>}

        <div className="mt-3 flex items-center justify-between text-xs">
          <span className="text-slate-500 dark:text-slate-400">
            {count === 0 ? 'No shots placed yet' : `${count} shot${count === 1 ? '' : 's'} placed`}
          </span>
          {count > 0 && (
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => removeAt(count - 1)}
                disabled={mutation.isPending}
                className="flex items-center gap-1 text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Undo2 size={13} /> Undo last
              </button>
              <button
                type="button"
                onClick={() => setPoints([])}
                disabled={mutation.isPending}
                className="text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Clear all
              </button>
            </div>
          )}
        </div>

        {mutation.isError && (
          <p className="text-red-500 dark:text-red-400 text-sm mt-3">{(mutation.error as Error).message}</p>
        )}

        <div className="flex gap-3 justify-end pt-4">
          <button
            type="button"
            onClick={close}
            disabled={mutation.isPending}
            className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-300 dark:border-slate-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => mutation.mutate(points)}
            disabled={count === 0 || mutation.isPending}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed press"
          >
            {mutation.isPending ? 'Adding…' : count > 1 ? `Add ${count} bullets` : 'Add bullet'}
          </button>
        </div>
      </div>
    </div>
  )
}
