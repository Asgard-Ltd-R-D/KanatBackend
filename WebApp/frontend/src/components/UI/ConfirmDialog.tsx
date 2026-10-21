interface Props {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  loadingLabel?: string
  onConfirm: () => void
  onCancel: () => void
  loading?: boolean
  error?: string // why the last confirm failed
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Delete',
  loadingLabel = 'Deleting…',
  onConfirm,
  onCancel,
  loading = false,
  error,
}: Props) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/30 dark:bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-2xl w-full max-w-md p-6">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">{title}</h3>
        <p className="text-slate-600 dark:text-slate-400 text-sm mb-6">{message}</p>
        {error && <p className="text-red-500 dark:text-red-400 text-sm -mt-3 mb-4">{error}</p>}
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-300 dark:border-slate-700 rounded-lg transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading ? loadingLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
