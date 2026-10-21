import clsx from 'clsx'
import { ServiceState, useSystemStatus } from '../hooks/useSystemStatus'

const STATE: Record<ServiceState, { label: string; dot: string; text: string }> = {
  online: { label: 'Online', dot: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' },
  offline: { label: 'Offline', dot: 'bg-red-500', text: 'text-red-600 dark:text-red-400' },
  unknown: { label: '—', dot: 'bg-slate-300 dark:bg-slate-600', text: 'text-slate-400 dark:text-slate-500' },
}

function Row({ name, state }: { name: string; state: ServiceState }) {
  const style = STATE[state]
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
        <span className={clsx('w-1.5 h-1.5 rounded-full', style.dot)} />
        {name}
      </span>
      <span className={clsx('font-medium', style.text)}>{style.label}</span>
    </div>
  )
}

// Sidebar indicator: is the backend up, and does it reach the video service
export function ConnectionStatus() {
  const { backend, videoService } = useSystemStatus()
  return (
    <div className="px-4 py-3 border-t border-slate-200 dark:border-slate-800 space-y-1.5">
      <Row name="Backend" state={backend} />
      <Row name="Video service" state={videoService} />
    </div>
  )
}
