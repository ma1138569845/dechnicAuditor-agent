import { describe, expect, it } from 'vitest'

import { computeDesks, deskContentBounds, SCENE_HEIGHT, SCENE_WIDTH } from './layout'

describe('computeDesks', () => {
  it('centers a small roster inside the usable vertical band', () => {
    const desks = computeDesks(3)
    expect(desks).toHaveLength(3)
    const ys = desks.map(d => d.y)
    const mid = (Math.min(...ys) + Math.max(...ys)) / 2
    expect(mid).toBeGreaterThan(SCENE_HEIGHT * 0.35)
    expect(mid).toBeLessThan(SCENE_HEIGHT * 0.7)
    expect(desks.every(d => d.x > 0 && d.x < SCENE_WIDTH)).toBe(true)
  })

  it('wraps to a second row past four desks', () => {
    const desks = computeDesks(5)
    expect(desks).toHaveLength(5)
    expect(new Set(desks.map(d => d.row)).size).toBe(2)
  })
})

describe('deskContentBounds', () => {
  it('returns a padded box around desks, not the full scene', () => {
    const desks = computeDesks(2)
    const bounds = deskContentBounds(desks)
    expect(bounds.w).toBeLessThan(SCENE_WIDTH)
    expect(bounds.h).toBeLessThan(SCENE_HEIGHT)
    expect(bounds.w).toBeGreaterThan(200)
    expect(bounds.h).toBeGreaterThan(150)
  })
})
