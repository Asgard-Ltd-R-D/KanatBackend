interface Props {
  status: 'active' | 'completed'
}

export function StatusBadge({ status }: Props) {
  if (status === 'active') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        Active
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium uppercase tracking-wider bg-slate-800 text-slate-400 border border-slate-700">
      <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
      Completed
    </span>
  )
}
