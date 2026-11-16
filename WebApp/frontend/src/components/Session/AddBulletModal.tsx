import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Undo2 } from 'lucide-react'
import { createBullet } from '../../api/bullets'
import { BulletHole, Run } from '../../types'
import { holesOver } from '../../utils/overlay'
import targetImg from '../../assets/target.png'

// The target artwork is authored at this pixel size, and a Bullet Hole's
// position is stored in these same template coordinates. So a click on the
// image maps straight to a position: no calibration, no homography.
const TEMPLATE_W = 1405
const TEMPLATE_H = 1120

// A placed shot: its position plus a stable idempotency key, fixed when placed
// so a retry of a partly-failed batch does not duplicate it
type Point = { x: number; y: number; key: string }

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
    mutation.reset()
    onClose()
  }

  // Turn a click on the image into template coordinates (the displayed size may
  // be scaled down; the image's natural size is the template space 1:1)
  function handleClick(e: React.MouseEvent<HTMLImageElement>) {
    if (mutation.isPending) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * TEMPLATE_W
    const y = ((e.clientY - rect.top) / rect.height) * TEMPLATE_H
    setPoints(ps => [...ps, { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10, key: crypto.randomUUID() }])
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
  const latestRun = runs[runs.length - 1]
  const contextPoints = latestRun
    ? holesOver(latestRun, runs, context)
    : context.map(b => [b.position_x, b.position_y] as [number, number])

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
          <img
            src={targetImg}
            alt="Target"
            width={TEMPLATE_W}
            height={TEMPLATE_H}
            draggable={false}
            onClick={handleClick}
            style={{ aspectRatio: `${TEMPLATE_W} / ${TEMPLATE_H}` }}
            className="block w-full h-auto cursor-crosshair"
          />

          {/* Existing holes, faint, for context */}
          {context.map((b, i) => (
            <span
              key={b.id}
              className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-black"
              style={{ left: `${(contextPoints[i][0] / TEMPLATE_W) * 100}%`, top: `${(contextPoints[i][1] / TEMPLATE_H) * 100}%` }}
              title={`#${b.rank}`}
            />
          ))}

          {/* The shots being placed — small red dots, matching the model's hole
              size; click one to remove it */}
          {points.map((p, i) => (
            <button
              key={p.key}
              type="button"
              onClick={() => removeAt(i)}
              title="Remove this shot"
              className="no-press absolute -translate-x-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-red-600 ring-1 ring-white hover:bg-red-700 transition-colors"
              style={{ left: `${(p.x / TEMPLATE_W) * 100}%`, top: `${(p.y / TEMPLATE_H) * 100}%` }}
            />
          ))}
        </div>

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
