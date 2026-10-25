import { Pencil, Trash2, Video } from 'lucide-react'
import { Camera } from '../../types'
import { CameraStatusBadge } from '../Camera/CameraStatusBadge'
import { Toggle } from '../UI/Toggle'

interface Props {
  camera: Camera
  onEdit: () => void
  onDelete: () => void
  onToggleEnabled: (enabled: boolean) => void
  toggling: boolean
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-medium uppercase tracking-wider text-slate-400 dark:text-slate-400">{label}</dt>
      <dd className="text-sm font-mono text-slate-700 dark:text-slate-300 truncate" title={value}>{value}</dd>
    </div>
  )
}

// One camera as a row: who it is, where its stream comes from, and its controls
export function CameraCard({ camera, onEdit, onDelete, onToggleEnabled, toggling }: Props) {
  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-5 py-4 shadow-sm dark:shadow-none flex items-center gap-6">
      <div className="flex items-center gap-3 w-56 shrink-0 min-w-0">
        <div className="w-9 h-9 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0">
          <Video size={16} className="text-slate-500 dark:text-slate-400" />
        </div>
        <div className="min-w-0">
          <p className="font-semibold text-slate-900 dark:text-slate-100 truncate mb-0.5" title={camera.alias}>{camera.alias}</p>
          <CameraStatusBadge status={camera.status} />
        </div>
      </div>

      <dl className="flex-1 grid grid-cols-3 gap-6 min-w-0">
        <Detail label="Multicast group" value={`${camera.mcast_ip}:${camera.mcast_port}`} />
        <Detail label="Interface" value={camera.iface ?? 'auto'} />
        <Detail label="Stream path" value={`:8554/${camera.alias}`} />
      </dl>

      <div className="flex items-center gap-1 shrink-0">
        <Toggle
          checked={camera.enabled}
          onChange={onToggleEnabled}
          disabled={toggling}
          label={camera.enabled ? `Disable ${camera.alias}` : `Enable ${camera.alias}`}
        />
        <button
          onClick={onEdit}
          className="ml-3 p-1.5 text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 rounded transition-colors"
          title="Edit camera"
        >
          <Pencil size={14} />
        </button>
        <button
          onClick={onDelete}
          className="p-1.5 text-slate-400 dark:text-slate-500 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-400/10 rounded transition-colors"
          title="Delete camera"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}
