import { useQuery } from '@tanstack/react-query'
import { getStatus } from '../api/status'

// As KanatFrontend checked MediaMTX: every 3 s, giving up after 2 s (api/status.ts)
const POLL_MS = 3000

export type ServiceState = 'online' | 'offline' | 'unknown'

type ServiceStates = {
  backend: ServiceState
  videoService: ServiceState
  detectionService: ServiceState
  // What the detector runs on and with, e.g. "CUDA · kanat_yolo26m_v1"; null unless the service is up
  detector: string | null
}

const toState = (up: boolean): ServiceState => (up ? 'online' : 'offline')

// The detector's folder name, shown short and tidy: drop the "kanat_" prefix and
// the trailing version, spaces for underscores, "YOLO" in caps.
// "kanat_yolo26n_v1" -> "YOLO26n"
function formatModel(name: string | null | undefined): string | null {
  if (!name) return null
  return name
    .replace(/^kanat_/, '')
    .replace(/_v[\d.]+$/i, '')
    .replace(/_/g, ' ')
    .replace(/yolo/gi, 'YOLO')
}

// Whether the backend, the video service and the Detection Service are up,
// checked every POLL_MS, and the detector the Detection Service runs. When the
// backend does not answer, the others are unknown.
export function useSystemStatus(): ServiceStates {
  const { data, isError, isPending } = useQuery({
    queryKey: ['status'],
    queryFn: getStatus,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    retry: false, // a missed answer shows straight away
  })

  if (isPending) return { backend: 'unknown', videoService: 'unknown', detectionService: 'unknown', detector: null }
  if (isError) return { backend: 'offline', videoService: 'unknown', detectionService: 'unknown', detector: null }
  // The device without its index: the PC has one GPU, so "cuda:0" reads "CUDA"
  const device = data.detector_device?.split(':')[0].toUpperCase()
  const detector = [device, formatModel(data.detector_model)].filter(Boolean).join(' · ')
  return {
    backend: 'online',
    videoService: toState(data.video_service),
    detectionService: toState(data.detection_service),
    detector: data.detection_service && detector ? detector : null,
  }
}
