import type { GraphCamera } from './graph-camera'
import { worldToScreen } from './graph-camera'
import type { SimLink, SimNode } from './graph-sim'

export interface GraphPalette {
  accent: string
  bg: string
  dark: boolean
  muted: string
  node: string
  stroke: string
  text: string
}

export interface GraphScene {
  camera: GraphCamera
  height: number
  hoverId: null | string
  links: SimLink[]
  matchIds: Set<string> | null
  neighborIds: Set<string> | null
  nodes: SimNode[]
  palette: GraphPalette
  selectedId: null | string
  showLabels: boolean
  width: number
}

export function typeFill(type: string, dark: boolean): string {
  let hash = 2166136261

  for (let index = 0; index < type.length; index += 1) {
    hash ^= type.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }

  const hue = (hash >>> 0) % 360
  const sat = dark ? 42 : 48
  const light = dark ? 64 : 42

  return `hsl(${hue} ${sat}% ${light}%)`
}

export function hitNode(nodes: SimNode[], wx: number, wy: number): SimNode | null {
  for (let index = nodes.length - 1; index >= 0; index -= 1) {
    const node = nodes[index]
    const dx = node.x - wx
    const dy = node.y - wy
    const hit = node.radius + 4

    if (dx * dx + dy * dy <= hit * hit && Number.isFinite(node.x) && Number.isFinite(node.y)) {
      return node
    }
  }

  return null
}

export function drawGraph(ctx: CanvasRenderingContext2D, scene: GraphScene): void {
  const { camera, height, palette, width } = scene

  ctx.clearRect(0, 0, width, height)

  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'

  for (const link of scene.links) {
    const ends = endsOf(link)

    if (!ends || !isDrawable(ends.source) || !isDrawable(ends.target)) {
      continue
    }

    const dimmed = isDimmed(ends.source.id, scene) || isDimmed(ends.target.id, scene)
    const from = worldToScreen(ends.source.x, ends.source.y, camera, width, height)
    const to = worldToScreen(ends.target.x, ends.target.y, camera, width, height)

    if (!isDrawablePoint(from) || !isDrawablePoint(to)) {
      continue
    }

    ctx.beginPath()
    ctx.moveTo(from.x, from.y)
    ctx.lineTo(to.x, to.y)
    ctx.strokeStyle = dimmed ? fade(palette.stroke, 0.18) : fade(palette.stroke, 0.55)
    ctx.lineWidth = dimmed ? 1 : 1.25
    ctx.stroke()
  }

  for (const node of scene.nodes) {
    if (!isDrawable(node)) {
      continue
    }

    const pos = worldToScreen(node.x, node.y, camera, width, height)

    if (!isDrawablePoint(pos)) {
      continue
    }

    const dimmed = isDimmed(node.id, scene)
    const selected = scene.selectedId === node.id
    const hovered = scene.hoverId === node.id
    const radius = (node.radius + (selected || hovered ? 1.5 : 0)) * camera.k
    const fill = typeFill(node.type, scene.palette.dark)
    const drawRadius = Math.max(2.5, Number.isFinite(radius) ? radius : 2.5)

    ctx.beginPath()
    ctx.arc(pos.x, pos.y, drawRadius, 0, Math.PI * 2)
    ctx.globalAlpha = dimmed ? 0.22 : 1
    ctx.fillStyle = fill
    ctx.fill()
    ctx.globalAlpha = 1

    if (selected || hovered) {
      ctx.strokeStyle = palette.accent
      ctx.lineWidth = selected ? 2 : 1.25
      ctx.stroke()
    }
  }

  ctx.font = `${Math.max(10, 11 * Math.min(Number.isFinite(camera.k) ? camera.k : 1, 1.3))}px ui-sans-serif, system-ui, sans-serif`
  ctx.textBaseline = 'middle'

  for (const node of scene.nodes) {
    if (!isDrawable(node) || !shouldLabel(node, scene)) {
      continue
    }

    const pos = worldToScreen(node.x, node.y, camera, width, height)

    if (!isDrawablePoint(pos)) {
      continue
    }
    const dimmed = isDimmed(node.id, scene)
    const label = node.name
    const textX = pos.x + Math.max(2.5, node.radius * camera.k) + 6
    const widthPx = ctx.measureText(label).width

    ctx.fillStyle = fade(palette.bg, 0.82)
    ctx.fillRect(textX - 3, pos.y - 8, widthPx + 6, 16)
    ctx.fillStyle = dimmed ? palette.muted : palette.text
    ctx.fillText(label, textX, pos.y)
  }
}

function endsOf(link: SimLink): null | { source: SimNode; target: SimNode } {
  if (typeof link.source === 'string' || typeof link.target === 'string') {
    return null
  }

  return { source: link.source, target: link.target }
}

function isDrawable(node: SimNode): boolean {
  return Number.isFinite(node.x) && Number.isFinite(node.y) && Number.isFinite(node.radius)
}

function isDrawablePoint(point: { x: number; y: number }): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.y) && Math.abs(point.x) < 1e6 && Math.abs(point.y) < 1e6
}

function isDimmed(id: string, scene: GraphScene): boolean {
  if (scene.matchIds && !scene.matchIds.has(id)) {
    return true
  }

  if (scene.neighborIds && !scene.neighborIds.has(id)) {
    return true
  }

  return false
}

function shouldLabel(node: SimNode, scene: GraphScene): boolean {
  if (scene.selectedId === node.id || scene.hoverId === node.id) {
    return true
  }

  if (scene.neighborIds?.has(node.id)) {
    return true
  }

  if (scene.matchIds?.has(node.id) && scene.camera.k >= 0.7) {
    return true
  }

  return scene.showLabels && scene.camera.k >= 1.15 && scene.nodes.length <= 120
}

export function resolveCssRgba(cssColor: string): null | { a: number; b: number; g: number; r: number } {
  if (typeof document === 'undefined' || !cssColor) {
    return null
  }

  const canvas = document.createElement('canvas')

  canvas.width = 1
  canvas.height = 1
  const ctx = canvas.getContext('2d', { willReadFrequently: true })

  if (!ctx) {
    return null
  }

  ctx.clearRect(0, 0, 1, 1)
  ctx.fillStyle = '#888888'
  ctx.fillStyle = cssColor
  ctx.fillRect(0, 0, 1, 1)
  const data = ctx.getImageData(0, 0, 1, 1).data

  return { a: data[3] / 255, b: data[2], g: data[1], r: data[0] }
}

export function resolveCssColor(cssColor: string, fallback: string): string {
  const rgba = resolveCssRgba(cssColor)

  if (!rgba || rgba.a < 0.2) {
    return fallback
  }

  return `rgb(${rgba.r}, ${rgba.g}, ${rgba.b})`
}

function fade(color: string, alpha: number): string {
  if (color.startsWith('rgba(')) {
    return color.replace(/rgba\(([^)]+)\)/, (_, inner: string) => {
      const parts = inner.split(',').map(part => part.trim())

      return `rgba(${parts[0]}, ${parts[1]}, ${parts[2]}, ${alpha})`
    })
  }

  if (color.startsWith('rgb(')) {
    return color.replace('rgb(', 'rgba(').replace(')', `, ${alpha})`)
  }

  return color
}
