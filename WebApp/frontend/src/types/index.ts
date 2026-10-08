export interface Session {
  id: string
  name: string
  status: 'active' | 'completed'
  started_at: string
  ended_at: string | null
  created_at: string
  bullet_holes?: BulletHole[]
  bullet_count?: number
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
