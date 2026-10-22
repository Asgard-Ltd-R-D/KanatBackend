import { useRef, useState } from 'react'
import { recordingVideoUrl } from '../../api/recordings'
import { BulletHole, CameraRecording, Run } from '../../types'
import { placeAt } from '../../utils/overlay'
import { Overlay, OverlayContent, OverlayToggle } from '../Camera/Overlay'
import { RecordingPartPicker } from './RecordingPartPicker'

interface Props {
  sessionId: string
  recording: CameraRecording
  runs: Run[] // the Session's Runs that watched this camera
  bullets: BulletHole[]
  startPart?: number
  startOffsetS?: number // where in startPart to begin
  onPosition?: (iso: string) => void // the moment on screen, as it plays
}

// The Overlay at the moment `at` (ms) (ADR-0009): the Run watching then, at
// its place then, with the Bullet Holes first seen by then. None while no Run
// watched
function overlayAt(runs: Run[], bullets: BulletHole[], at: number): OverlayContent | null {
  for (const run of runs) {
    const place = placeAt(run, at)
    if (place) return { view: run.baseline_view, place, bullets: bullets.filter(b => Date.parse(b.first_seen_at) <= at) }
  }
  return null
}

// One camera's whole recording. A recording stopped and started again comes in
// parts: they are picked with RecordingPartPicker, and each one runs into the next
export function ReplayPlayer({ sessionId, recording, runs, bullets, startPart = 0, startOffsetS = 0, onPosition }: Props) {
  const [part, setPart] = useState(startPart)
  const videoRef = useRef<HTMLVideoElement>(null)
  // The moment on screen, in ms
  const [at, setAt] = useState<number | null>(null)
  // On whenever the player opens: never remembered
  const [showOverlay, setShowOverlay] = useState(true)
  const overlay = at === null ? null : overlayAt(runs, bullets, at)
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
      {/* Keyed with its part, so the Overlay measures each part's video */}
      <div key={`${recording.alias}-${span.start}`} className="relative">
        <video
          ref={videoRef}
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
            const moment = new Date(span.start).getTime() + e.currentTarget.currentTime * 1000
            setAt(moment)
            onPosition?.(new Date(moment).toISOString())
          }}
          onEnded={() => {
            if (part < last) setPart(part + 1)
          }}
          className="w-full aspect-video bg-black rounded-xl"
        />
        {overlay && showOverlay && <Overlay {...overlay} videoRef={videoRef} />}
        {/* Top right: the bottom is the video's own controls */}
        {runs.length > 0 && <OverlayToggle checked={showOverlay} onChange={setShowOverlay} className="absolute top-3 right-3" />}
      </div>
    </div>
  )
}
