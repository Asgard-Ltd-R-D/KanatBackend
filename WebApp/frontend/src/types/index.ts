export interface Session {
  id: string
  name: string
  status: 'active' | 'completed'
  started_at: string
  ended_at: string | null
  record: boolean // the cameras are recorded while this session is active
  camera_id?: string | null // the camera whose stream detection watches; fixed at creation
  created_at: string
  bullet_holes?: BulletHole[]
  bullet_count?: number
  detection?: Detection // on a single session, not in the list
  grouping?: Grouping // on a single session, not in the list
  runs?: Run[] // on a single session, in taken_at order, not in the list
}

// Where a Run's baseline frame showed the Board in the camera's picture (ADR-0009)
export interface BaselineView {
  taken_at: string
  picture: { width: number; height: number }
  template_to_picture: number[][] // template px -> the baseline frame's px, row-major 3x3
  targets: [number, number][][] // one outline per Target, in template px; its index is target_index
  baseline_marks: [number, number][] // one point per Baseline Mark, in template px
}

// Where a Run's registered Look showed the Board in the camera's picture (ADR-0009)
export interface Place {
  at: string
  template_to_picture: number[][] // template px -> that frame's px, row-major 3x3
}

// A Run of the Detection Service that watched the session, and the camera it watched
export interface Run {
  camera_alias: string
  taken_at: string
  watched_until: string // its latest Look's frame time the backend read, registered or Lost
  baseline_view: BaselineView
  places: Place[] // where it registered the Board, in time order, starting with the baseline's
}

// One Target's Group, in mm from the Target's centre. The spread measures are
// null below two Bullet Holes
export interface Group {
  target_index: number
  n: number
  mpi_x_mm: number
  mpi_y_mm: number
  cep_mm: number | null
  mean_radius_mm: number | null
  rms_radius_mm: number | null
  extreme_spread_mm: number | null
}

// Computed by the backend from the session's Bullet Holes: one Group per
// Target, and the Bullet Holes left out of every Group
export interface Grouping {
  groups: Group[]
  misses: number
  without_position: number // manual ones, and detected ones without a print scale
}

// Whether a Run of the Detection Service watches a session. none: no camera,
// or the session has ended. end_unconfirmed: the session ended without the
// Detection Service confirming it ended its Run, so the last shots may be missing
export interface Detection {
  state: 'none' | 'starting' | 'watching' | 'not_watching' | 'ending' | 'end_unconfirmed'
  // Why not watching: the Detection Service did not answer, the Run failed to
  // start on the camera's stream, another session's Run holds the service, or
  // the session's camera was disabled or deleted. null for a Run lost while
  // the service answers, until it is started again
  reason: 'service_down' | 'stream_failed' | 'other_session' | 'camera_disabled' | null
  detail: string | null // the Detection Service's own words for a refused start
}

export interface BulletHole {
  id: string
  session_id: string
  rank: number
  first_seen_at: string
  position_x: number
  position_y: number
  target_index: number | null
  x_mm: number | null
  y_mm: number | null
  source: 'model' | 'manual'
  created_at: string
}

export interface BulletCreatePayload {
  version: string
  first_seen_at: string
  position: { x: number; y: number }
  target_index?: number | null
  x_mm?: number | null
  y_mm?: number | null
  source: 'model' | 'manual'
}

export type StreamStatus = 'loading' | 'playing' | 'error'

export interface WhepSession {
  answerSdp: string
  resourceUrl: string | null // DELETE this to end the session
}

// Pushed by the backend as Server-Sent Events from /sessions/{id}/live
export type LiveEvent =
  | { type: 'bullet_created'; bullet: BulletHole }
  | { type: 'bullet_deleted'; bullet_id: string }
  | { type: 'session_updated'; name: string; status: Session['status']; ended_at: string | null; record: boolean }
  | { type: 'detection_updated'; detection: Detection }
  | { type: 'run_moved'; taken_at: string } // a Run kept a new place: the refetch brings it

// live: MediaMTX is receiving the stream. no_signal: configured, but nothing
// arrives on its multicast group. disabled: switched off in Settings.
// unreachable: the video service did not answer.
export type CameraStatus = 'live' | 'no_signal' | 'disabled' | 'unreachable'

// What the operator enters for a camera multicasting H.264 RTP
export interface CameraInput {
  alias: string
  mcast_ip: string
  mcast_port: number
  iface: string | null // network interface to join the group on; null: the OS chooses
  enabled: boolean
}

export interface Camera extends CameraInput {
  id: string
  created_at: string
  status: CameraStatus
}

export interface RecordingSpan {
  start: string
  duration_s: number
}

// What one camera recorded during a session
export interface CameraRecording {
  alias: string
  spans: RecordingSpan[]
}

// From GET /status: whether the backend reaches the video service (MediaMTX)
// and the Detection Service. The backend answering at all is its own status.
export interface SystemStatus {
  video_service: boolean
  detection_service: boolean
}
