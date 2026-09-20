import assert from 'node:assert/strict'
import test from 'node:test'

import { circuitTransform } from '../src/lib/trackGeometry.ts'

const bounds = points => ({
  width: Math.max(...points.map(point => point.x)) - Math.min(...points.map(point => point.x)),
  height: Math.max(...points.map(point => point.y)) - Math.min(...points.map(point => point.y)),
})

test('portrait circuits rotate to a consistent landscape display span', () => {
  const raw = [{ x: -2_900, y: -13_700 }, { x: 2_900, y: 13_700 }, { x: 0, y: 0 }]
  const transform = circuitTransform(raw)
  assert.ok(transform)
  assert.equal(transform.portrait, true)
  const display = raw.map(transform.apply)
  assert.deepEqual(bounds(display), { width: 10_000, height: 2116.7883211678833 })
})

test('track and car coordinates use the same transform', () => {
  const raw = [{ x: 0, y: 0 }, { x: 10_000, y: 0 }, { x: 10_000, y: 5_000 }]
  const transform = circuitTransform(raw)
  assert.ok(transform)
  assert.equal(transform.portrait, false)
  assert.deepEqual(transform.apply({ x: 5_000, y: 2_500 }), { x: 0, y: -0 })
  assert.deepEqual(bounds(raw.map(transform.apply)), { width: 10_000, height: 5_000 })
})
