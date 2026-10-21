import { CameraRecording } from '../types'

// Where in a session's recordings a moment can be watched
export interface ReplayMoment {
  alias: string
  part: number
  offsetS: number // seconds into that part
}

const spanEnd = (start: string, durationS: number) => new Date(start).getTime() + durationS * 1000

// Parts of one unbroken recording meet end to start; the backend's microseconds
// round to milliseconds here
const CONTIGUOUS_MS = 2

// The first camera and part that recorded `iso`, starting `prerollS` earlier:
// in the part before if the recording ran on unbroken from it, else no earlier
// than the part's start. Null if no camera was recording then
export function findMoment(recordings: CameraRecording[], iso: string, prerollS = 0): ReplayMoment | null {
  const at = new Date(iso).getTime()
  for (const recording of recordings) {
    const spans = recording.spans
    let part = spans.findIndex(s => new Date(s.start).getTime() <= at && at < spanEnd(s.start, s.duration_s))
    if (part >= 0) {
      const from = at - prerollS * 1000
      while (
        part > 0 &&
        from < new Date(spans[part].start).getTime() &&
        Math.abs(new Date(spans[part].start).getTime() - spanEnd(spans[part - 1].start, spans[part - 1].duration_s)) <= CONTIGUOUS_MS
      ) {
        part--
      }
      const offsetS = (from - new Date(spans[part].start).getTime()) / 1000
      return { alias: recording.alias, part, offsetS: Math.max(0, offsetS) }
    }
  }
  return null
}

// A camera's recording at a glance: from, to, and how much was recorded
export function summarize(recording: CameraRecording): { from: string; to: string; recordedS: number } {
  const first = recording.spans[0]
  const last = recording.spans[recording.spans.length - 1]
  return {
    from: first.start,
    to: new Date(spanEnd(last.start, last.duration_s)).toISOString(),
    recordedS: recording.spans.reduce((sum, s) => sum + s.duration_s, 0),
  }
}
