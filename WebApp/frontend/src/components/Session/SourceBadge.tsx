import { Bot, User } from 'lucide-react'

// Who reported a Bullet Hole: the detection model (AI) or the operator (M)
export function SourceBadge({ source }: { source: 'model' | 'manual' }) {
  if (source === 'model') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-semibold tracking-wide bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/20">
        <Bot size={9} />
        AI
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-semibold tracking-wide bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-500/20">
      <User size={9} />
      M
    </span>
  )
}
