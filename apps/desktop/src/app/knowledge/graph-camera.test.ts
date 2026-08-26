import { describe, expect, it } from 'vitest'

import { fitCamera, screenToWorld, worldToScreen, zoomCameraAt, type GraphCamera } from './graph-camera'

const camera: GraphCamera = { k: 2, x: 10, y: -4 }

describe('graph camera', () => {
  it('round-trips world and screen coordinates', () => {
    const world = { x: 40, y: -12 }
    const screen = worldToScreen(world.x, world.y, camera, 800, 600)
    const back = screenToWorld(screen.x, screen.y, camera, 800, 600)

    expect(back.x).toBeCloseTo(world.x)
    expect(back.y).toBeCloseTo(world.y)
  })

  it('keeps the world point under the cursor when zooming', () => {
    const sx = 120
    const sy = 80
    const before = screenToWorld(sx, sy, camera, 800, 600)
    const zoomed = zoomCameraAt(camera, sx, sy, 800, 600, 1.5)
    const after = screenToWorld(sx, sy, zoomed, 800, 600)

    expect(after.x).toBeCloseTo(before.x)
    expect(after.y).toBeCloseTo(before.y)
    expect(zoomed.k).toBeCloseTo(3)
  })

  it('fits the bounding box into the viewport', () => {
    const fitted = fitCamera(
      [
        { x: -100, y: -50 },
        { x: 100, y: 50 }
      ],
      400,
      300
    )

    expect(fitted.x).toBe(0)
    expect(fitted.y).toBe(0)
    expect(fitted.k).toBeGreaterThan(0)
    expect(fitted.k).toBeLessThanOrEqual(1.6)
  })

  it('ignores non-finite points so fit never produces NaN', () => {
    const fitted = fitCamera(
      [
        { x: Number.POSITIVE_INFINITY, y: 0 },
        { x: 10, y: 20 },
        { x: Number.NaN, y: 3 }
      ],
      400,
      300
    )

    expect(fitted.x).toBe(10)
    expect(fitted.y).toBe(20)
    expect(Number.isFinite(fitted.k)).toBe(true)
  })
})
