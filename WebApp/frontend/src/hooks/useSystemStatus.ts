import { useQuery } from '@tanstack/react-query'
import { getStatus } from '../api/status'

// As KanatFrontend checked MediaMTX: every 3 s, giving up after 2 s (api/status.ts)
const POLL_MS = 3000

export type ServiceState = 'online' | 'offline' | 'unknown'

// Whether the backend and the video service are up, checked every POLL_MS.
// When the backend does not answer, the video service's state is unknown.
export function useSystemStatus(): { backend: ServiceState; videoService: ServiceState } {
  const { data, isError, isPending } = useQuery({
    queryKey: ['status'],
    queryFn: getStatus,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    retry: false, // a missed answer shows straight away
  })

  if (isPending) return { backend: 'unknown', videoService: 'unknown' }
  if (isError) return { backend: 'offline', videoService: 'unknown' }
  return { backend: 'online', videoService: data.video_service ? 'online' : 'offline' }
}
