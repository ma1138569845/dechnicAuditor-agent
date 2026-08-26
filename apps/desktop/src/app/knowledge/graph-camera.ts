export interface GraphCamera {
  k: number
  x: number
  y: number
}

export const GRAPH_ZOOM_MIN = 0.15
export const GRAPH_ZOOM_MAX = 4

export function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value))
}

export function screenToWorld(
  sx: number,
  sy: number,
  camera: GraphCamera,
  width: number,
  height: number
): { x: number; y: number } {
  return {
    x: (sx - width / 2) / camera.k + camera.x,
    y: (sy - height / 2) / camera.k + camera.y
  }
}

export function worldToScreen(
  wx: number,
  wy: number,
  camera: GraphCamera,
  width: number,
  height: number
): { x: number; y: number } {
  return {
    x: (wx - camera.x) * camera.k + width / 2,
    y: (wy - camera.y) * camera.k + height / 2
  }
}

export function zoomCameraAt(
  camera: GraphCamera,
  sx: number,
  sy: number,
  width: number,
  height: number,
  factor: number
): GraphCamera {
  const world = screenToWorld(sx, sy, camera, width, height)
  const k = clamp(camera.k * factor, GRAPH_ZOOM_MIN, GRAPH_ZOOM_MAX)

  return {
    k,
    x: world.x - (sx - width / 2) / k,
    y: world.y - (sy - height / 2) / k
  }
}

export function fitCamera(
  points: { x: number; y: number }[],
  width: number,
  height: number,
  pad = 48
): GraphCamera {
  if (points.length === 0 || width <= 0 || height <= 0) {
    return { k: 1, x: 0, y: 0 }
  }

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity

  for (const point of points) {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) {
      continue
    }

    minX = Math.min(minX, point.x)
    minY = Math.min(minY, point.y)
    maxX = Math.max(maxX, point.x)
    maxY = Math.max(maxY, point.y)
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
    return { k: 1, x: 0, y: 0 }
  }

  const spanX = Math.max(maxX - minX, 40)
  const spanY = Math.max(maxY - minY, 40)
  const k = clamp(Math.min((width - pad * 2) / spanX, (height - pad * 2) / spanY), GRAPH_ZOOM_MIN, 1.6)

  return {
    k,
    x: (minX + maxX) / 2,
    y: (minY + maxY) / 2
  }
}
