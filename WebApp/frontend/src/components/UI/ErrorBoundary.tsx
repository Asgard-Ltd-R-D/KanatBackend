import { Component, ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { log } from '../../utils/logger'

// A screen that crashes shows this instead of going blank, and the crash is
// logged with where it happened. The sidebar stays usable around it.
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    log.error('A screen crashed', { error: error.message, stack: error.stack, component_stack: info.componentStack })
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="h-full flex items-center justify-center p-8">
        <div className="max-w-md text-center">
          <AlertTriangle size={28} className="mx-auto text-red-500" />
          <h2 className="mt-4 text-base font-semibold text-slate-900 dark:text-slate-100">Something went wrong on this screen</h2>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            It has been logged. Open another page from the sidebar, or reload.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="mt-5 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors"
          >
            Reload
          </button>
        </div>
      </div>
    )
  }
}
