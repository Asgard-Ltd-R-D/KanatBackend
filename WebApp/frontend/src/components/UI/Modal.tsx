import { ReactNode, useEffect } from 'react'
import { X } from 'lucide-react'
import clsx from 'clsx'

interface Props {
  open: boolean
  title: string
  subtitle?: string
  size?: 'md' | 'xl' // xl: for a video
  headerExtra?: ReactNode // controls beside the title
  onClose: () => void
  children: ReactNode
}

export function Modal({ open, title, subtitle, size = 'md', headerExtra, onClose, children }: Props) {
  // Esc closes it
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/30 dark:bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div
        className={clsx(
          'relative bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-2xl w-full p-6',
          size === 'xl' ? 'max-w-5xl' : 'max-w-md',
        )}
      >
        <div className="flex items-start justify-between gap-4 mb-5">
          <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
            {subtitle && <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{subtitle}</p>}
          </div>
          <div className="flex items-center gap-3">
            {headerExtra}
            <button onClick={onClose} className="text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors">
              <X size={20} />
            </button>
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}
