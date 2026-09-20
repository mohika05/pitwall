export interface CircuitPoint {
  x: number
  y: number
}

export interface CircuitTransform {
  portrait: boolean
  scale: number
  apply: (point: CircuitPoint) => CircuitPoint
}

const DISPLAY_SPAN = 10_000

export function circuitTransform(points: CircuitPoint[]): CircuitTransform | null {
  if (points.length === 0) return null

  const xs = points.map(point => point.x)
  const ys = points.map(point => point.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const width = maxX - minX
  const height = maxY - minY
  const span = Math.max(width, height)
  if (!Number.isFinite(span) || span <= 0) return null

  const centreX = (minX + maxX) / 2
  const centreY = (minY + maxY) / 2
  const portrait = height > width
  const scale = DISPLAY_SPAN / span

  return {
    portrait,
    scale,
    apply(point) {
      const x = (point.x - centreX) * scale
      const y = (point.y - centreY) * scale

      // FastF1 circuits do not share a display orientation. Rotate portrait
      // layouts so the timing map uses its wide panel consistently, then flip
      // Y because SVG coordinates grow downwards.
      return portrait
        ? { x: y, y: x }
        : { x, y: -y }
    },
  }
}
