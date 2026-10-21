import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createCamera, updateCamera } from '../../api/cameras'
import { Camera } from '../../types'
import { Modal } from '../UI/Modal'
import { Toggle } from '../UI/Toggle'
import {
  CameraForm, CameraFormErrors, EMPTY_CAMERA_FORM, toForm, toInput, validateCamera,
} from '../../utils/cameraValidation'

interface Props {
  open: boolean
  camera: Camera | null // null: adding a new one
  onClose: () => void
}

const INPUT =
  'w-full bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-blue-500'

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">{label}</label>
      {children}
      {error && <p className="text-red-500 dark:text-red-400 text-xs mt-1">{error}</p>}
    </div>
  )
}

export function CameraFormModal({ open, camera, onClose }: Props) {
  const qc = useQueryClient()
  const [form, setForm] = useState<CameraForm>(EMPTY_CAMERA_FORM)
  const [errors, setErrors] = useState<CameraFormErrors>({})

  // Start from the camera being edited, or blank, each time the form opens
  useEffect(() => {
    if (!open) return
    setForm(camera ? toForm(camera) : EMPTY_CAMERA_FORM)
    setErrors({})
  }, [open, camera])

  const mutation = useMutation({
    mutationFn: () => (camera ? updateCamera(camera.id, toInput(form)) : createCamera(toInput(form))),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cameras'] })
      onClose()
    },
  })

  // A failed save from the last time the form was open is not this one's
  const { reset } = mutation
  useEffect(() => {
    if (open) reset()
  }, [open, reset])

  const set = (field: keyof CameraForm) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [field]: e.target.value }))

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const found = validateCamera(form)
    setErrors(found)
    if (Object.keys(found).length === 0) mutation.mutate()
  }

  return (
    <Modal
      open={open}
      title={camera ? `Edit ${camera.alias}` : 'Add Camera'}
      onClose={onClose}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* The name is the camera's stream and recordings name, so it is set once */}
        <Field label="Name" error={errors.alias}>
          <input
            autoFocus={!camera}
            value={form.alias}
            onChange={set('alias')}
            readOnly={!!camera}
            title={camera ? "A camera's name cannot be changed: it names its stream and recordings" : undefined}
            placeholder="e.g. lane1"
            className={`${INPUT} ${camera ? 'opacity-60 cursor-not-allowed' : ''}`}
          />
        </Field>

        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2">
            <Field label="Multicast group" error={errors.mcast_ip}>
              <input value={form.mcast_ip} onChange={set('mcast_ip')} placeholder="226.226.226.112" className={`${INPUT} font-mono`} />
            </Field>
          </div>
          <Field label="Port" error={errors.mcast_port}>
            <input value={form.mcast_port} onChange={set('mcast_port')} inputMode="numeric" placeholder="112" className={`${INPUT} font-mono`} />
          </Field>
        </div>

        <Field label="Network interface (optional)" error={errors.iface}>
          <input value={form.iface} onChange={set('iface')} placeholder="Automatic" className={`${INPUT} font-mono`} />
        </Field>

        <div className="flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-2.5">
          <p className="text-sm font-medium text-slate-700 dark:text-slate-300">Enabled</p>
          <Toggle checked={form.enabled} onChange={enabled => setForm(f => ({ ...f, enabled }))} label="Enabled" />
        </div>

        {mutation.isError && (
          <p className="text-red-500 dark:text-red-400 text-sm">{(mutation.error as Error).message}</p>
        )}

        <div className="flex gap-3 justify-end pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-300 dark:border-slate-700 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50"
          >
            {mutation.isPending ? 'Saving…' : camera ? 'Save Changes' : 'Add Camera'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
