import { RefObject, useEffect, useState } from 'react'
import { BaselineView, BulletHole } from '../../types'
import { Point, Size, baselineMarksToDraw, labelGroups, templateToElement } from '../../utils/overlay'

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

// What the Overlay draws: a Run's Baseline View at one of its places (its
// template_to_picture), and the Bullet Holes over it
export interface OverlayContent {
  view: BaselineView
  place: number[][]
  bullets: BulletHole[]
}

// The Overlay (ADR-0009), where the Run's place puts things on the
// picture: each Target's outline, labelled with its number, each Bullet Hole
// as a ring numbered with its rank (one label for rings too close to number
// apart), and in grey each Baseline Mark no Bullet Hole stands for. It covers the video exactly, and lets every click through
// to the player.
export function Overlay({ view, place, bullets, videoRef }: OverlayContent & { videoRef: RefObject<HTMLVideoElement> }) {
  const sizes = useVideoSizes(videoRef)
  const toElement = sizes && templateToElement(place, view.picture, sizes.video, sizes.element)
  if (!toElement) return null
  const holes = bullets.map(b => [b.position_x, b.position_y] as Point)
  const markers = holes.map(toElement)

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
      {bullets.map((b, i) => (
        <circle key={b.id} cx={markers[i][0]} cy={markers[i][1]} r={MARKER_RADIUS} fill="none" stroke={colourOf(b)} strokeWidth={2} />
      ))}
      {labelGroups(markers, 2 * MARKER_RADIUS).map(group => {
        // Top right of the group's rings, where a lone ring's label goes
        const x = Math.max(...group.map(i => markers[i][0])) + MARKER_RADIUS + 2
        const y = Math.min(...group.map(i => markers[i][1])) - MARKER_RADIUS + 2
        return (
          <text key={bullets[group[0]].id} x={x} y={y} fontSize={12} fontWeight={700} {...textOutline}>
            {/* By rank: the list is in first_seen_at order, and a rank is the order holes arrived in */}
            {group.sort((a, b) => bullets[a].rank - bullets[b].rank).map((i, n) => (
              <tspan key={bullets[i].id} fill={colourOf(bullets[i])}>
                {n > 0 && ','}
                {bullets[i].rank}
              </tspan>
            ))}
          </text>
        )
      })}
    </svg>
  )
}
