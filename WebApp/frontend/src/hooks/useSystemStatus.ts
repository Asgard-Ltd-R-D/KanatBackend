import { useQuery } from '@tanstack/react-query'
import { getStatus } from '../api/status'

// As KanatFrontend checked MediaMTX: every 3 s, giving up after 2 s (api/status.ts)
const POLL_MS = 3000

export type ServiceState = 'online' | 'offline' | 'unknown'

type ServiceStates = { backend: ServiceState; videoService: ServiceState; detectionService: ServiceState }

const toState = (up: boolean): ServiceState => (up ? 'online' : 'offline')

// Whether the backend, the video service and the Detection Service are up,
// checked every POLL_MS. When the backend does not answer, the others are unknown.
export function useSystemStatus(): ServiceStates {
  const { data, isError, isPending } = useQuery({
    queryKey: ['status'],
    queryFn: getStatus,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    retry: false, // a missed answer shows straight away
  })

  if (isPending) return { backend: 'unknown', videoService: 'unknown', detectionService: 'unknown' }
  if (isError) return { backend: 'offline', videoService: 'unknown', detectionService: 'unknown' }
  return {
    backend: 'online',
    videoService: toState(data.video_service),
    detectionService: toState(data.detection_service),
  }
}
