interface Props {
  score: number
  size?: 'sm' | 'md'
}

const SCORE_STYLES: Record<number, { bg: string; text: string; border: string }> = {
  10: { bg: 'bg-yellow-400/20', text: 'text-yellow-300', border: 'border-yellow-400/40' },
  9:  { bg: 'bg-orange-400/20', text: 'text-orange-300', border: 'border-orange-400/40' },
  8:  { bg: 'bg-red-500/20',    text: 'text-red-400',    border: 'border-red-500/40' },
  7:  { bg: 'bg-blue-500/20',   text: 'text-blue-400',   border: 'border-blue-500/40' },
  6:  { bg: 'bg-purple-500/20', text: 'text-purple-400', border: 'border-purple-500/40' },
  0:  { bg: 'bg-slate-700/50',  text: 'text-slate-400',  border: 'border-slate-600/40' },
}

export function scoreColor(score: number): string {
  const colors: Record<number, string> = {
    10: '#FFD700',
    9:  '#FFA500',
    8:  '#EF4444',
    7:  '#3B82F6',
    6:  '#8B5CF6',
    0:  '#6B7280',
  }
  return colors[score] ?? '#6B7280'
}

export function ScoreBadge({ score, size = 'sm' }: Props) {
  const styles = SCORE_STYLES[score] ?? SCORE_STYLES[0]
  const padding = size === 'md' ? 'px-3 py-1 text-sm' : 'px-2 py-0.5 text-xs'

  return (
    <span
      className={`inline-flex items-center justify-center rounded font-semibold border ${padding} ${styles.bg} ${styles.text} ${styles.border}`}
    >
      {score === 0 ? 'MISS' : score}
    </span>
  )
}
