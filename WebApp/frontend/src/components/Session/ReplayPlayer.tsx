import { useRef, useState } from 'react'
import { recordingVideoUrl } from '../../api/recordings'
import { CameraRecording } from '../../types'
import { RecordingPartPicker } from './RecordingPartPicker'

interface Props {
  sessionId: string
  recording: CameraRecording
  startPart?: number
  startOffsetS?: number // where in startPart to begin
  onPosition?: (iso: string) => void // the moment on screen, as it plays
}

// One camera's whole recording. A recording stopped and started again comes in
// parts: they are picked with RecordingPartPicker, and each one runs into the next
export function ReplayPlayer({ sessionId, recording, startPart = 0, startOffsetS = 0, onPosition }: Props) {
  const [part, setPart] = useState(startPart)
  // Where to seek once the opening part has loaded; used once
  const seekTo = useRef<number | null>(startOffsetS > 0 ? startOffsetS : null)

  const span = recording.spans[part] ?? recording.spans[0]
  const last = recording.spans.length - 1

  const choose = (next: number) => {
    seekTo.current = null
    setPart(next)
  }

  return (
    <div>
      {recording.spans.length > 1 && (
        <div className="flex justify-end mb-3">
          <RecordingPartPicker spans={recording.spans} part={part} onChange={choose} />
        </div>
      )}
      <video
        key={`${recording.alias}-${span.start}`}
        controls
        autoPlay
        src={recordingVideoUrl(sessionId, recording.alias, span)}
        onLoadedMetadata={e => {
          if (seekTo.current !== null) {
            e.currentTarget.currentTime = seekTo.current
            seekTo.current = null
          }
        }}
        onTimeUpdate={e => {
          const at = new Date(span.start).getTime() + e.currentTarget.currentTime * 1000
          onPosition?.(new Date(at).toISOString())
        }}
        onEnded={() => {
          if (part < last) setPart(part + 1)
        }}
        className="w-full aspect-video bg-black rounded-xl"
      />
    </div>
  )
}
