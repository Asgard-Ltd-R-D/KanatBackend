import { useRef } from 'react'
import clsx from 'clsx'
import { CameraRecording } from '../../types'
import { Modal } from '../UI/Modal'
import { ReplayPlayer } from './ReplayPlayer'
import { findMoment } from '../../utils/recordings'

export interface ReplayTarget {
  alias: string
  part?: number
  offsetS?: number
}

interface Props {
  sessionId: string
  recordings: CameraRecording[]
  target: ReplayTarget | null
  onChange: (target: ReplayTarget | null) => void
}

// A session's recordings in a large window over the page; Esc closes it
export function ReplayModal({ sessionId, recordings, target, onChange }: Props) {
  const recording = recordings.find(r => r.alias === target?.alias)
  // The moment on screen, so switching camera shows the same moment from the
  // other camera, when it was recording then; otherwise from its start
  const position = useRef<string | null>(null)

  const switchTo = (alias: string) => {
    const other = recordings.find(r => r.alias === alias)
    const moment = other && position.current ? findMoment([other], position.current) : null
    onChange(moment ? { alias, part: moment.part, offsetS: moment.offsetS } : { alias })
  }

  const cameraSwitch = recordings.length > 1 && (
    <div className="flex rounded-lg border border-slate-200 dark:border-slate-700 p-0.5">
      {recordings.map(r => (
        <button
          key={r.alias}
          onClick={() => r.alias !== target?.alias && switchTo(r.alias)}
          className={clsx(
            'px-3 py-1 rounded-md text-xs font-mono transition-colors',
            r.alias === target?.alias
              ? 'bg-blue-50 dark:bg-blue-600/20 text-blue-600 dark:text-blue-400'
              : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200',
          )}
        >
          {r.alias}
        </button>
      ))}
    </div>
  )

  return (
    <Modal
      open={!!recording}
      title={recordings.length > 1 ? 'Replay' : `Replay · ${recording?.alias ?? ''}`}
      size="xl"
      headerExtra={cameraSwitch}
      onClose={() => {
        position.current = null
        onChange(null)
      }}
    >
      {recording && (
        <ReplayPlayer
          // A new player for each camera and moment, so its first render
          // already has the right part (no stray download of another one)
          key={`${recording.alias}-${target?.part ?? 0}-${target?.offsetS ?? 0}`}
          sessionId={sessionId}
          recording={recording}
          startPart={target?.part ?? 0}
          startOffsetS={target?.offsetS ?? 0}
          onPosition={iso => (position.current = iso)}
        />
      )}
    </Modal>
  )
}
