import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Crosshair, Plus } from 'lucide-react'
import { retakeBaseline } from '../../api/sessions'
import { deleteBullet } from '../../api/bullets'
import { BulletHole, Session } from '../../types'
import { Board } from '../../utils/boards'
import { ConfirmDialog } from '../UI/ConfirmDialog'
import { DetectionBadge } from './DetectionBadge'
import { GroupsCard } from './GroupsCard'
import { BulletLog } from './BulletLog'
import { AddBulletModal } from './AddBulletModal'

// Detection states in which a board's baseline may be retaken (the backend
// refuses it while a Run is starting or ending)
const RETAKEABLE = ['none', 'watching', 'not_watching']

// The label for a board's tab: the camera's alias, or "No board" for the holes
// on no board (alias null)
const boardLabel = (alias: string | null) => alias ?? 'No board'

// One board's section: its detection state, a retake-baseline button, its Group,
// its Bullet Log (filtered to this board), and a manual-add posting to this board.
// A Session watches every enabled camera, so there is one board per camera, shown
// as tabs when there is more than one.
export function BoardTabs({ session, boards }: { session: Session; boards: Board[] }) {
  const qc = useQueryClient()
  const [selected, setSelected] = useState(0)
  const [addFor, setAddFor] = useState<string | null | undefined>(undefined) // undefined: closed
  const [deleteTarget, setDeleteTarget] = useState<BulletHole | null>(null)
  const active = session.status === 'active'

  const baselineMutation = useMutation({
    mutationFn: (camera: string) => retakeBaseline(session.id, camera),
    onSuccess: s => qc.setQueryData(['session', session.id], s),
  })

  const deleteBulletMutation = useMutation({
    mutationFn: (bulletId: string) => deleteBullet(session.id, bulletId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['session', session.id] })
      qc.invalidateQueries({ queryKey: ['sessions'] })
      setDeleteTarget(null)
    },
  })

  if (boards.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-900 border border-dashed border-slate-300 dark:border-slate-700 rounded-xl py-10 text-center">
        <p className="text-sm text-slate-500">
          No boards: enable a camera in Settings, or add a bullet by hand once the session is complete.
        </p>
        {/* A completed Session with no camera still takes manual holes on no board */}
        {!active && (
          <button
            onClick={() => setAddFor(null)}
            className="mt-4 inline-flex items-center gap-2 px-3 py-2 bg-blue-50 dark:bg-blue-600/10 hover:bg-blue-100 dark:hover:bg-blue-600/20 border border-blue-200 dark:border-blue-600/30 text-blue-700 dark:text-blue-400 text-sm font-medium rounded-lg transition-colors"
          >
            <Plus size={14} />
            Add Bullet
          </button>
        )}
        <AddBulletModal
          open={addFor !== undefined}
          sessionId={session.id}
          camera={addFor ?? null}
          onClose={() => setAddFor(undefined)}
          onSuccess={() => {}}
        />
      </div>
    )
  }

  const board = boards[Math.min(selected, boards.length - 1)]
  const showDetection = active || board.detection.state === 'end_unconfirmed'

  return (
    <div>
      {/* One tab per board, when there is more than one */}
      {boards.length > 1 && (
        <div className="flex gap-1 mb-4 border-b border-slate-200 dark:border-slate-800">
          {boards.map((b, i) => (
            <button
              key={b.alias ?? '__none__'}
              onClick={() => setSelected(i)}
              className={
                'px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ' +
                (i === Math.min(selected, boards.length - 1)
                  ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200')
              }
            >
              {boardLabel(b.alias)}
              <span className="ml-1.5 text-xs text-slate-400">({b.bullets.length})</span>
            </button>
          ))}
        </div>
      )}

      {/* The selected board */}
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">{boardLabel(board.alias)}</h2>
          {showDetection && <DetectionBadge detection={board.detection} />}
        </div>

        <div className="flex items-center gap-2">
          {active && board.camera && (
            <button
              onClick={() => baselineMutation.mutate(board.camera!.alias)}
              // Not while a Run is starting or ending on this board: the backend refuses it then
              disabled={
                (baselineMutation.isPending && baselineMutation.variables === board.camera.alias) ||
                !RETAKEABLE.includes(board.detection.state)
              }
              title="After re-hanging this board's sheet: detection restarts from what the camera sees now. Hold fire until Detection ready."
              className="flex items-center gap-2 px-3 py-2 bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Crosshair size={14} />
              Retake baseline
            </button>
          )}

          {/* Manual holes only after the session ends: the backend refuses a
              manual bullet while the session is active (it would 409) */}
          {!active && (
            <button
              onClick={() => setAddFor(board.alias)}
              className="flex items-center gap-2 px-3 py-2 bg-blue-50 dark:bg-blue-600/10 hover:bg-blue-100 dark:hover:bg-blue-600/20 border border-blue-200 dark:border-blue-600/30 text-blue-700 dark:text-blue-400 text-sm font-medium rounded-lg transition-colors"
            >
              <Plus size={14} />
              Add Bullet
            </button>
          )}
        </div>
      </div>

      {/* Group statistics once the session is complete: while it is active the
          live bullet feed updates the holes but not the groupings, so the card
          would read stale (as it did before: it showed only when completed) */}
      {!active && board.grouping && <GroupsCard grouping={board.grouping} />}

      <BulletLog bullets={board.bullets} onDelete={setDeleteTarget} />

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Bullet"
        message={`Delete bullet #${deleteTarget?.rank ?? ''}?`}
        confirmLabel="Delete"
        onConfirm={() => deleteTarget && deleteBulletMutation.mutate(deleteTarget.id)}
        onCancel={() => {
          setDeleteTarget(null)
          deleteBulletMutation.reset()
        }}
        loading={deleteBulletMutation.isPending}
        error={deleteBulletMutation.error?.message}
      />

      <AddBulletModal
        open={addFor !== undefined}
        sessionId={session.id}
        camera={addFor ?? null}
        onClose={() => setAddFor(undefined)}
        onSuccess={() => {}}
      />
    </div>
  )
}
