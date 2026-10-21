import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Circle, Square } from 'lucide-react'
import { updateSession } from '../../api/sessions'
import { Session } from '../../types'

// Recording state of an active session, with the switch to start or stop it
export function RecordingControl({ session }: { session: Session }) {
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: (record: boolean) => updateSession(session.id, { record }),
    onSuccess: (updated) => qc.setQueryData<Session>(['session', session.id], s => s && { ...s, record: updated.record }),
  })

  const button = session.record ? (
    <button
      onClick={() => mutation.mutate(false)}
      disabled={mutation.isPending}
      title="Stop recording"
      className="flex items-center gap-2 px-4 py-2 bg-red-50 dark:bg-red-500/10 hover:bg-red-100 dark:hover:bg-red-500/20 border border-red-200 dark:border-red-500/30 text-red-700 dark:text-red-400 text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
    >
      <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
      Recording
      <Square size={12} className="ml-1 opacity-70" />
    </button>
  ) : (
    <button
      onClick={() => mutation.mutate(true)}
      disabled={mutation.isPending}
      title="Start recording"
      className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
    >
      <Circle size={12} className="text-red-500 fill-red-500" />
      Record
    </button>
  )

  return (
    <div className="relative">
      {button}
      {mutation.isError && (
        <p className="absolute right-0 top-full mt-1 whitespace-nowrap text-xs text-red-500 dark:text-red-400" title={mutation.error.message}>
          Couldn't change recording
        </p>
      )}
    </div>
  )
}
