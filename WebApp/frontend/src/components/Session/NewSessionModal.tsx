import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Crosshair, Video } from 'lucide-react'
import { createSession } from '../../api/sessions'
import { useCameras } from '../../hooks/useCameras'
import { Modal } from '../UI/Modal'
import { Toggle } from '../UI/Toggle'

interface Props {
  open: boolean
  onClose: () => void
}

export function NewSessionModal({ open, onClose }: Props) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [record, setRecord] = useState(false)
  const [cameraId, setCameraId] = useState('') // '': no camera, no detection
  const { data: cameras } = useCameras()

  useEffect(() => {
    if (!open) return
    setName('')
    setRecord(false)
    setCameraId('')
  }, [open])

  const mutation = useMutation({
    mutationFn: () => createSession(name.trim() || 'Unnamed Session', record, cameraId || null),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ['sessions'] })
      onClose()
      navigate(`/sessions/${session.id}`)
    },
  })

  // A failed start from the last time the form was open is not this one's
  const { reset } = mutation
  useEffect(() => {
    if (open) reset()
  }, [open, reset])

  return (
    <Modal open={open} title="New Session" onClose={onClose}>
      <input
        autoFocus
        type="text"
        value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && !mutation.isPending && mutation.mutate()}
        placeholder="Session name"
        className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-blue-500 mb-4"
      />

      {/* The camera watching the Board: detection watches its stream for the whole session */}
      <div className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-2.5 mb-3">
        <div className="flex items-center gap-3">
          <Crosshair size={16} className="text-slate-400 dark:text-slate-500 shrink-0" />
          <p className="text-sm font-medium text-slate-700 dark:text-slate-300">Detection camera</p>
        </div>
        <select
          value={cameraId}
          onChange={e => setCameraId(e.target.value)}
          aria-label="Detection camera"
          className="bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-md px-2 py-1 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:border-blue-500"
        >
          <option value="">None</option>
          {cameras?.filter(c => c.enabled).map(c => (
            <option key={c.id} value={c.id}>{c.alias}</option>
          ))}
        </select>
      </div>

      <div className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-2.5 mb-5">
        <div className="flex items-center gap-3">
          <Video size={16} className="text-slate-400 dark:text-slate-500 shrink-0" />
          <p className="text-sm font-medium text-slate-700 dark:text-slate-300">Record video</p>
        </div>
        <Toggle checked={record} onChange={setRecord} label="Record video" />
      </div>

      {mutation.isError && (
        <p className="text-red-500 dark:text-red-400 text-sm mb-4">{(mutation.error as Error).message}</p>
      )}

      <div className="flex gap-3 justify-end">
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-300 dark:border-slate-700 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50"
        >
          {mutation.isPending ? 'Creating…' : 'Start Session'}
        </button>
      </div>
    </Modal>
  )
}
