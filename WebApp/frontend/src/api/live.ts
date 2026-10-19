import { API_URL } from '../utils/config'

// A Session's live events, as Server-Sent Events from the backend
export function openSessionLive(sessionId: string): EventSource {
  return new EventSource(`${API_URL}/sessions/${sessionId}/live`)
}
