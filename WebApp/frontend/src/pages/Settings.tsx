import { CamerasPanel } from '../components/Settings/CamerasPanel'

export function Settings() {
  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100 mb-8">Settings</h1>

      <CamerasPanel />
    </div>
  )
}
