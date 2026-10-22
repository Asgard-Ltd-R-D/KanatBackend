import clsx from 'clsx'
import { Detection } from '../../types'

const STYLES: Record<Exclude<Detection['state'], 'none'>, { label: string; badge: string; dot: string }> = {
  starting: {
    label: 'Detection starting',
    badge: 'bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/30',
    dot: 'bg-amber-500 dark:bg-amber-400 animate-pulse',
  },
  watching: {
    label: 'Detection ready',
    badge: 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/30',
    dot: 'bg-emerald-500 dark:bg-emerald-400',
  },
  not_watching: {
    label: 'Not watching',
    badge: 'bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/30',
    dot: 'bg-red-500 dark:bg-red-400',
  },
  ending: {
    label: 'Closing…',
    badge: 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700',
    dot: 'bg-slate-400 dark:bg-slate-500 animate-pulse',
  },
}

const REASONS: Record<NonNullable<Detection['reason']>, string> = {
  service_down: 'Detection Service down',
  stream_failed: 'the camera stream failed',
  other_session: 'another session is being watched',
  camera_disabled: 'the camera is disabled or deleted',
}

// Whether detection watches the session: shots count once it reads "Detection ready"
export function DetectionBadge({ detection }: { detection: Detection }) {
  if (detection.state === 'none') return null
  const style = STYLES[detection.state]
  return (
    <span
      title={detection.detail ?? undefined}
      className={clsx('inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border', style.badge)}
    >
      <span className={clsx('w-1.5 h-1.5 rounded-full', style.dot)} />
      {detection.reason ? `${style.label}: ${REASONS[detection.reason]}` : style.label}
    </span>
  )
}
