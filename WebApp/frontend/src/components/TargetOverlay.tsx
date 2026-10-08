import { useState } from 'react'
import targetPng from '../assets/target.png'
import { BulletHole } from '../types'

interface TooltipData {
  x: number
  y: number
  bullet: BulletHole
}

interface Props {
  bullets: BulletHole[]
}

const TPL_W = 1405
const TPL_H = 1120

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function TargetOverlay({ bullets }: Props) {
  const [tooltip, setTooltip] = useState<TooltipData | null>(null)

  return (
    <div className="relative w-full select-none">
      <img
        src={targetPng}
        alt="Target"
        className="w-full h-auto rounded-lg block"
        draggable={false}
      />
      <svg
        viewBox={`0 0 ${TPL_W} ${TPL_H}`}
        preserveAspectRatio="xMidYMid meet"
        className="absolute inset-0 w-full h-full"
        style={{ top: 0, left: 0 }}
      >
        {bullets.map((b) => {
          const cx = b.position_x
          const cy = b.position_y
          const label = String(b.rank)
          const fontSize = label.length > 1 ? 52 : 60

          return (
            <g
              key={b.id}
              onMouseEnter={(e) => {
                const rect = (e.currentTarget.closest('svg') as SVGElement).getBoundingClientRect()
                const svgX = (cx / TPL_W) * rect.width
                const svgY = (cy / TPL_H) * rect.height
                setTooltip({ x: svgX, y: svgY, bullet: b })
              }}
              onMouseLeave={() => setTooltip(null)}
              style={{ cursor: 'pointer' }}
            >
              <circle cx={cx} cy={cy} r={55} fill="#3b82f6" stroke="white" strokeWidth={8} opacity={0.9} />
              <text
                x={cx}
                y={cy + fontSize * 0.35}
                textAnchor="middle"
                fontSize={fontSize}
                fontWeight="bold"
                fill="white"
                style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
              >
                {label}
              </text>
            </g>
          )
        })}
      </svg>

      {tooltip && (
        <div
          className="absolute z-10 pointer-events-none"
          style={{ left: Math.min(tooltip.x + 12, 999), top: Math.max(tooltip.y - 80, 0) }}
        >
          <div className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 shadow-xl text-xs whitespace-nowrap">
            <div className="font-semibold text-slate-100 mb-1">Bullet #{tooltip.bullet.rank}</div>
            <div className="text-slate-400">
              Time: <span className="text-slate-200 font-medium">{formatTime(tooltip.bullet.first_seen_at)}</span>
            </div>
            <div className="text-slate-400">
              Pos:{' '}
              <span className="text-slate-200 font-mono text-[10px]">
                {tooltip.bullet.position_x.toFixed(1)}, {tooltip.bullet.position_y.toFixed(1)}
              </span>
            </div>
          </div>
        </div>
      )}

      {bullets.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="bg-slate-900/80 backdrop-blur-sm rounded-lg px-4 py-2 text-slate-400 text-sm">
            No bullets detected
          </div>
        </div>
      )}
    </div>
  )
}
