import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Plus, RefreshCw, Video } from 'lucide-react'
import { deleteCamera, updateCamera } from '../../api/cameras'
import { useCameras } from '../../hooks/useCameras'
import { Camera } from '../../types'
import { ConfirmDialog } from '../UI/ConfirmDialog'
import { CameraCard } from './CameraCard'
import { CameraFormModal } from './CameraFormModal'

export function CamerasPanel() {
  const qc = useQueryClient()
  const { data: cameras, isLoading, isError, refetch } = useCameras({ watch: true })
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Camera | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Camera | null>(null)

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteCamera(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cameras'] })
      setDeleteTarget(null)
    },
  })

  const enableMutation = useMutation({
    mutationFn: ({ camera, enabled }: { camera: Camera; enabled: boolean }) =>
      updateCamera(camera.id, {
        alias: camera.alias,
        mcast_ip: camera.mcast_ip,
        mcast_port: camera.mcast_port,
        iface: camera.iface,
        enabled,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cameras'] }),
  })

  const openForm = (camera: Camera | null) => {
    setEditing(camera)
    setFormOpen(true)
  }

  return (
    <section>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Cameras</h2>
        <button
          onClick={() => openForm(null)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors shadow-lg shadow-blue-600/20"
        >
          <Plus size={16} />
          Add Camera
        </button>
      </div>

      {isLoading && (
        <div className="grid gap-3">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl h-[76px] animate-pulse" />
          ))}
        </div>
      )}

      {isError && !cameras && (
        <div className="flex flex-col items-center gap-3 py-12">
          <AlertCircle size={32} className="text-red-500 dark:text-red-400" />
          <p className="text-slate-600 dark:text-slate-400 text-sm">Failed to load cameras</p>
          <button onClick={() => refetch()} className="flex items-center gap-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm font-medium rounded-lg transition-colors">
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      )}

      {cameras && cameras.length === 0 && (
        <div className="bg-white dark:bg-slate-900 border border-dashed border-slate-300 dark:border-slate-700 rounded-xl flex flex-col items-center gap-3 py-14">
          <Video size={32} className="text-slate-300 dark:text-slate-700" />
          <p className="text-slate-600 dark:text-slate-400 font-medium">No cameras yet</p>
        </div>
      )}

      {cameras && cameras.length > 0 && (
        <div className="grid gap-3">
          {cameras.map(camera => (
            <CameraCard
              key={camera.id}
              camera={camera}
              onEdit={() => openForm(camera)}
              onDelete={() => setDeleteTarget(camera)}
              onToggleEnabled={enabled => enableMutation.mutate({ camera, enabled })}
              toggling={enableMutation.isPending && enableMutation.variables?.camera.id === camera.id}
            />
          ))}
        </div>
      )}

      <CameraFormModal open={formOpen} camera={editing} onClose={() => setFormOpen(false)} />

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Camera"
        message={`Delete "${deleteTarget?.alias ?? ''}"?`}
        confirmLabel="Delete"
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        onCancel={() => {
          setDeleteTarget(null)
          deleteMutation.reset()
        }}
        loading={deleteMutation.isPending}
        error={deleteMutation.error?.message}
      />
    </section>
  )
}
