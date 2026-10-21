import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createSession } from '../../api/sessions'
import { Modal } from '../UI/Modal'

interface Props {
  open: boolean
  onClose: () => void
}

export function NewSessionModal({ open, onClose }: Props) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [name, setName] = useState('')

  useEffect(() => {
    if (!open) return
    setName('')
  }, [open])

  const mutation = useMutation({
    mutationFn: () => createSession(name.trim() || 'Unnamed Session'),
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
