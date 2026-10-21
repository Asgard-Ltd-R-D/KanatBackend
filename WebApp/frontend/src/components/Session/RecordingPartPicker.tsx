import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { RecordingSpan } from '../../types'
import { formatClock, formatLength } from '../../utils/format'

interface Props {
  spans: RecordingSpan[]
  part: number
  onChange: (part: number) => void
}

const STEP =
  'p-1 rounded text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-800 dark:hover:text-slate-200 transition-colors disabled:opacity-30 disabled:pointer-events-none'

// Which part of an interrupted recording to play: a list of every part, with
// previous / next beside it. Stays one line however many parts there are.
export function RecordingPartPicker({ spans, part, onChange }: Props) {
  return (
    <div className="flex items-center gap-1 shrink-0">
      <button onClick={() => onChange(part - 1)} disabled={part === 0} className={STEP} title="Previous part">
        <ChevronLeft size={16} />
      </button>

      <div className="relative">
        <select
          value={part}
          onChange={e => onChange(Number(e.target.value))}
          aria-label="Recording part"
          className="appearance-none cursor-pointer rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 pl-3 pr-8 py-1 text-xs font-mono text-slate-700 dark:text-slate-200 focus:outline-none focus:border-blue-500"
        >
          {spans.map((s, i) => (
            <option key={s.start} value={i}>
              Part {i + 1} of {spans.length} · {formatClock(s.start)} · {formatLength(s.duration_s)}
            </option>
          ))}
        </select>
        <ChevronDown size={14} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
      </div>

      <button onClick={() => onChange(part + 1)} disabled={part === spans.length - 1} className={STEP} title="Next part">
        <ChevronRight size={16} />
      </button>
    </div>
  )
}
