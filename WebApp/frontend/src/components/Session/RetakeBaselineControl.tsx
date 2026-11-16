import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Crosshair, ChevronDown } from 'lucide-react'
import { retakeBaseline } from '../../api/sessions'
import { Session } from '../../types'
import { Board } from '../../utils/boards'

// Detection states in which a board's baseline may be retaken (the backend
// refuses it while a Run is starting or ending)
const RETAKEABLE = ['none', 'watching', 'not_watching']

const RETAKE_TITLE =
  "After re-hanging this board's sheet: detection restarts from what the camera sees now. Hold fire until Detection ready."

// The Retake baseline control for the live-session header, beside End Session.
// One camera: a plain button. Several: a dropdown to pick which board to retake.
export function RetakeBaselineControl({ session, boards }: { session: Session; boards: Board[] }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const mutation = useMutation({
    mutationFn: (camera: string) => retakeBaseline(session.id, camera),
    onSuccess: s => qc.setQueryData(['session', session.id], s),
  })

  // Close the dropdown on an outside click
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  // Only boards with a live camera can be retaken
  const live = boards.filter(b => b.camera)
  if (live.length === 0) return null

  const canRetake = (board: Board) =>
    RETAKEABLE.includes(board.detection.state) &&
    !(mutation.isPending && mutation.variables === board.camera!.alias)

  const btn =
    'flex items-center gap-2 px-4 py-2 bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 ' +
    'border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-sm font-medium rounded-lg ' +
    'transition-colors disabled:opacity-50 disabled:cursor-not-allowed'

  // One camera: a single button
  if (live.length === 1) {
    const board = live[0]
    return (
      <button onClick={() => mutation.mutate(board.camera!.alias)} disabled={!canRetake(board)} title={RETAKE_TITLE} className={btn}>
        <Crosshair size={14} />
        Retake baseline
      </button>
    )
  }

  // Several cameras: a dropdown of boards
  return (
    <div ref={menuRef} className="relative">
      <button onClick={() => setOpen(o => !o)} title={RETAKE_TITLE} className={btn}>
        <Crosshair size={14} />
        Retake baseline
        <ChevronDown size={14} className={open ? 'rotate-180 transition-transform' : 'transition-transform'} />
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-56 z-20 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg shadow-lg py-1">
          {live.map(board => (
            <button
              key={board.alias ?? '__none__'}
              onClick={() => {
                mutation.mutate(board.camera!.alias)
                setOpen(false)
              }}
              disabled={!canRetake(board)}
              className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span className="flex items-center gap-2">
                <Crosshair size={13} />
                {board.alias}
              </span>
              {!RETAKEABLE.includes(board.detection.state) && (
                <span className="text-xs text-slate-400">busy</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
