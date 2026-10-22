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
}

// Whether a Run of the Detection Service watches a session. none: no camera,
// or the session has ended.
export interface Detection {
  state: 'none' | 'starting' | 'watching' | 'not_watching' | 'ending'
  // Why not watching: the Detection Service did not answer, the Run failed to
  // start on the camera's stream, or another session's Run holds the service
  reason: 'service_down' | 'stream_failed' | 'other_session' | null
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
