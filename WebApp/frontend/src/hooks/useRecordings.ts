import { useQuery } from '@tanstack/react-query'
import { getRecordings } from '../api/recordings'

// After a failed load, how often to try again (the video service may be back)
const RETRY_MS = 5000

// What each camera recorded during a session
export function useRecordings(sessionId: string, enabled = true) {
  return useQuery({
    queryKey: ['recordings', sessionId],
    queryFn: () => getRecordings(sessionId),
    enabled,
    refetchInterval: query => (query.state.status === 'error' ? RETRY_MS : false),
  })
}
