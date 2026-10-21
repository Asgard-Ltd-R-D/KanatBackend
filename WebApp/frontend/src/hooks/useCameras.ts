import { useQuery } from '@tanstack/react-query'
import { getCameras } from '../api/cameras'

// How often a screen watching the cameras' state asks again
const STATUS_POLL_MS = 3000
// After a failed load, how often to try again (the backend may be restarting)
const RETRY_MS = 5000

// The cameras with each one's stream state. `watch` keeps the state fresh while
// the screen is open; a failed load is tried again either way.
export function useCameras({ watch = false }: { watch?: boolean } = {}) {
  return useQuery({
    queryKey: ['cameras'],
    queryFn: getCameras,
    refetchInterval: query => (watch ? STATUS_POLL_MS : query.state.status === 'error' ? RETRY_MS : false),
  })
}
