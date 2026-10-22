import { RefObject, useEffect, useState } from 'react'
import { BaselineView, BulletHole } from '../../types'
import { Point, Size, baselineMarksToDraw, templateToElement } from '../../utils/overlay'

const OUTLINE_COLOUR = '#22d3ee'
const BASELINE_MARK_COLOUR = '#94a3b8'
const TARGET_COLOUR = '#34d399'
const MISS_COLOUR = '#f87171'
const MANUAL_COLOUR = '#fbbf24' // the manual source badge's amber

// In screen px, whatever the picture's size
const MARKER_RADIUS = 9
const BASELINE_MARK_RADIUS = 7

function colourOf(b: BulletHole) {
  if (b.source === 'manual') return MANUAL_COLOUR
  return b.target_index !== null ? TARGET_COLOUR : MISS_COLOUR
}

// Text legible on any picture: outlined in black
const textOutline = { stroke: 'black', strokeWidth: 3, paintOrder: 'stroke' } as const

// The video's own size and its box's, followed as the player is resized and
// as the stream's picture loads or changes size
function useVideoSizes(videoRef: RefObject<HTMLVideoElement>) {
  const [sizes, setSizes] = useState<{ video: Size; element: Size } | null>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const measure = () =>
      setSizes({
        video: { width: video.videoWidth, height: video.videoHeight },
        element: { width: video.clientWidth, height: video.clientHeight },
      })
    measure()
    const box = new ResizeObserver(measure)
    box.observe(video)
    // Fired once the picture's size is known, and whenever it changes
    video.addEventListener('resize', measure)
    return () => {
      box.disconnect()
      video.removeEventListener('resize', measure)
    }
  }, [videoRef])

  return sizes
}

// What the Overlay draws: a Run's Baseline View, and the Bullet Holes over it
export interface OverlayContent {
  view: BaselineView
  bullets: BulletHole[]
}

// The Overlay (ADR-0009), where the Run's baseline placed things on the
// picture: each Target's outline, labelled with its number, each Bullet Hole
// as a ring numbered with its rank, and in grey each Baseline Mark no Bullet
// Hole stands for. It covers the video exactly, and lets every click through
// to the player.
export function Overlay({ view, bullets, videoRef }: OverlayContent & { videoRef: RefObject<HTMLVideoElement> }) {
  const sizes = useVideoSizes(videoRef)
  const toElement = sizes && templateToElement(view.template_to_picture, view.picture, sizes.video, sizes.element)
  if (!toElement) return null
  const holes = bullets.map(b => [b.position_x, b.position_y] as Point)

  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-none" aria-hidden>
      {view.targets.map((outline, i) => {
        const points = outline.map(toElement)
        if (points.length === 0) return null
        const top = points.reduce((a, b) => (b[1] < a[1] ? b : a))
        return (
          <g key={i}>
            <polygon
              points={points.map(p => p.join(',')).join(' ')}
              fill="none"
              stroke={OUTLINE_COLOUR}
              strokeWidth={2}
              strokeLinejoin="round"
            />
            <text
              x={top[0]}
              y={Math.max(top[1] - 6, 14)}
              textAnchor="middle"
              fontSize={12}
              fontWeight={600}
              fill={OUTLINE_COLOUR}
              {...textOutline}
            >
              Target {i + 1}
            </text>
          </g>
        )
      })}
      {baselineMarksToDraw(view.baseline_marks, holes).map((mark, i) => {
        const [x, y] = toElement(mark)
        return <circle key={i} cx={x} cy={y} r={BASELINE_MARK_RADIUS} fill="none" stroke={BASELINE_MARK_COLOUR} strokeWidth={1.5} />
      })}
      {bullets.map(b => {
        const [x, y] = toElement([b.position_x, b.position_y])
        const colour = colourOf(b)
        return (
          <g key={b.id}>
            <circle cx={x} cy={y} r={MARKER_RADIUS} fill="none" stroke={colour} strokeWidth={2} />
            <text x={x + MARKER_RADIUS + 2} y={y - MARKER_RADIUS + 2} fontSize={12} fontWeight={700} fill={colour} {...textOutline}>
              {b.rank}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
