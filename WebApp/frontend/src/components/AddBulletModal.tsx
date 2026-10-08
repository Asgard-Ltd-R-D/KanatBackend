import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { createBullet } from '../api/bullets'

interface Props {
  open: boolean
  sessionId: string
  onClose: () => void
  onSuccess: () => void
}

export function AddBulletModal({ open, sessionId, onClose, onSuccess }: Props) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ first_seen_at: '', position_x: '', position_y: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})

  const mutation = useMutation({
    mutationFn: () =>
      createBullet(sessionId, {
        version: 'v1',
        first_seen_at: new Date(form.first_seen_at).toISOString(),
        position: { x: Number(form.position_x), y: Number(form.position_y) },
        source: 'manual',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['session', sessionId] })
      onSuccess()
      onClose()
      setForm({ first_seen_at: '', position_x: '', position_y: '' })
      setErrors({})
    },
  })

  function validate(): boolean {
    const e: Record<string, string> = {}
    if (!form.first_seen_at || isNaN(new Date(form.first_seen_at).getTime())) e.first_seen_at = 'Required date/time'
    if (!form.position_x || isNaN(Number(form.position_x))) e.position_x = 'Required number'
    if (!form.position_y || isNaN(Number(form.position_y))) e.position_y = 'Required number'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (validate()) mutation.mutate()
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-slate-900 border border-slate-800 rounded-xl shadow-2xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="text-lg font-semibold text-slate-100">Add Bullet Manually</h3>
            <p className="text-xs text-slate-500 mt-0.5">Correction after session ended</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Detected At</label>
            <input
              type="datetime-local"
              step="1"
              value={form.first_seen_at}
              onChange={e => setForm(f => ({ ...f, first_seen_at: e.target.value }))}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
            />
            {errors.first_seen_at && <p className="text-red-400 text-xs mt-1">{errors.first_seen_at}</p>}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Position X (template px)</label>
              <input
                type="number"
                step="0.1"
                value={form.position_x}
                onChange={e => setForm(f => ({ ...f, position_x: e.target.value }))}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
                placeholder="0–1390"
              />
              {errors.position_x && <p className="text-red-400 text-xs mt-1">{errors.position_x}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Position Y (template px)</label>
              <input
                type="number"
                step="0.1"
                value={form.position_y}
                onChange={e => setForm(f => ({ ...f, position_y: e.target.value }))}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
                placeholder="0–1974"
              />
              {errors.position_y && <p className="text-red-400 text-xs mt-1">{errors.position_y}</p>}
            </div>
          </div>

          {mutation.isError && (
            <p className="text-red-400 text-sm">{(mutation.error as Error).message}</p>
          )}

          <div className="flex gap-3 justify-end pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50"
            >
              {mutation.isPending ? 'Adding…' : 'Add Bullet'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
