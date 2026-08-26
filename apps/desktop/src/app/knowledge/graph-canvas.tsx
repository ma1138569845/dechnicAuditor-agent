import { useEffect, useRef } from 'react'
import type { Simulation } from 'd3-force'

import { isPinchZoomWheel, isSmartZoomWheel } from '@/lib/trackpad-gestures'

import { fitCamera, screenToWorld, zoomCameraAt, type GraphCamera } from './graph-camera'
import { drawGraph, hitNode, type GraphPalette } from './graph-render'
import type { SimLink, SimNode } from './graph-sim'

interface GraphCanvasProps {
  ariaLabel: string
  camera: GraphCamera
  links: SimLink[]
  matchIds: Set<string> | null
  neighborIds: Set<string> | null
  nodes: SimNode[]
  onCameraChange: (camera: GraphCamera) => void
  onSelect: (id: null | string) => void
  palette: GraphPalette
  selectedId: null | string
  sim: Simulation<SimNode, SimLink>
  simAlphaTarget: (value: number) => void
}

export function GraphCanvas({
  ariaLabel,
  camera,
  links,
  matchIds,
  neighborIds,
  nodes,
  onCameraChange,
  onSelect,
  palette,
  selectedId,
  sim,
  simAlphaTarget
}: GraphCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const cameraRef = useRef(camera)
  const nodesRef = useRef(nodes)
  const linksRef = useRef(links)
  const hoverRef = useRef<null | string>(null)
  const matchRef = useRef(matchIds)
  const neighborRef = useRef(neighborIds)
  const paletteRef = useRef(palette)
  const selectedRef = useRef(selectedId)
  const scheduleRef = useRef<() => void>(() => undefined)
  const dragRef = useRef<null | { kind: 'node' | 'pan'; lastX: number; lastY: number; moved: boolean; node?: SimNode }>(
    null
  )

  cameraRef.current = camera
  nodesRef.current = nodes
  linksRef.current = links
  matchRef.current = matchIds
  neighborRef.current = neighborIds
  paletteRef.current = palette
  selectedRef.current = selectedId

  useEffect(() => {
    // Non-null assertion: the effect returns early when the canvas is missing,
    // so every listener closure below is only ever registered with a live node.
    const canvas = canvasRef.current!

    if (!canvas) {
      return
    }

    let ctx = canvas.getContext('2d')
    let frame = 0
    let dragging = false

    function schedule() {
      if (frame) {
        return
      }

      frame = requestAnimationFrame(() => {
        frame = 0
        paint()

        if (dragging) {
          schedule()
        }
      })
    }

    function paint() {
      const target = canvasRef.current

      if (!target || !ctx || typeof ctx.fillRect !== 'function') {
        return
      }

      const rect = target.getBoundingClientRect()

      if (rect.width < 2 || rect.height < 2) {
        return
      }

      const dpr = window.devicePixelRatio || 1
      const nextWidth = Math.max(1, Math.round(rect.width * dpr))
      const nextHeight = Math.max(1, Math.round(rect.height * dpr))

      if (target.width !== nextWidth || target.height !== nextHeight) {
        target.width = nextWidth
        target.height = nextHeight
        ctx = target.getContext('2d')

        if (!ctx) {
          return
        }
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      drawGraph(ctx, {
        camera: cameraRef.current,
        height: rect.height,
        hoverId: hoverRef.current,
        links: linksRef.current,
        matchIds: matchRef.current,
        neighborIds: neighborRef.current,
        nodes: nodesRef.current,
        palette: paletteRef.current,
        selectedId: selectedRef.current,
        showLabels: nodesRef.current.length <= 80,
        width: rect.width
      })
    }

    function onLost(event: Event) {
      event.preventDefault()
      ctx = null
    }

    function onRestored() {
      ctx = canvas.getContext('2d')
      schedule()
    }

    scheduleRef.current = schedule
    schedule()
    sim.on('tick.draw', schedule)
    canvas.addEventListener('contextlost', onLost)
    canvas.addEventListener('contextrestored', onRestored)

    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
            schedule()
          })

    observer?.observe(canvas)

    function point(event: PointerEvent) {
      const rect = canvas.getBoundingClientRect()

      return { x: event.clientX - rect.left, y: event.clientY - rect.top, w: rect.width, h: rect.height }
    }

    function onDown(event: PointerEvent) {
      if (event.button !== 0) {
        return
      }

      const p = point(event)
      const world = screenToWorld(p.x, p.y, cameraRef.current, p.w, p.h)
      const node = hitNode(nodesRef.current, world.x, world.y)

      canvas.setPointerCapture(event.pointerId)
      dragging = true
      schedule()

      if (node) {
        node.fx = node.x
        node.fy = node.y
        simAlphaTarget(0.25)
        dragRef.current = { kind: 'node', lastX: p.x, lastY: p.y, moved: false, node }
        onSelect(node.id)
      } else {
        dragRef.current = { kind: 'pan', lastX: p.x, lastY: p.y, moved: false }
      }
    }

    function onMove(event: PointerEvent) {
      const p = point(event)
      const drag = dragRef.current

      if (!drag) {
        const world = screenToWorld(p.x, p.y, cameraRef.current, p.w, p.h)
        const node = hitNode(nodesRef.current, world.x, world.y)
        const nextId = node?.id ?? null

        if (hoverRef.current !== nextId) {
          hoverRef.current = nextId
          schedule()
        }

        canvas.style.cursor = node ? 'pointer' : 'grab'

        return
      }

      const dx = p.x - drag.lastX
      const dy = p.y - drag.lastY

      if (Math.abs(dx) + Math.abs(dy) > 2) {
        drag.moved = true
      }

      drag.lastX = p.x
      drag.lastY = p.y

      if (drag.kind === 'pan') {
        const cam = cameraRef.current

        onCameraChange({ k: cam.k, x: cam.x - dx / cam.k, y: cam.y - dy / cam.k })
        canvas.style.cursor = 'grabbing'

        return
      }

      if (drag.node) {
        const world = screenToWorld(p.x, p.y, cameraRef.current, p.w, p.h)

        drag.node.fx = world.x
        drag.node.fy = world.y
        drag.node.x = world.x
        drag.node.y = world.y
      }
    }

    function onUp(event: PointerEvent) {
      const drag = dragRef.current

      dragRef.current = null
      dragging = false
      canvas.style.cursor = 'grab'
      schedule()

      if (drag?.kind === 'node') {
        simAlphaTarget(0)
      }

      if (drag && !drag.moved && drag.kind === 'pan') {
        onSelect(null)
      }

      try {
        canvas.releasePointerCapture(event.pointerId)
      } catch {
        /* already released */
      }
    }

    function onWheel(event: WheelEvent) {
      if (isSmartZoomWheel(event)) {
        event.preventDefault()
        const rect = canvas.getBoundingClientRect()
        const cam = fitCamera(
          nodesRef.current.map(node => ({ x: node.x, y: node.y })),
          rect.width,
          rect.height
        )

        onCameraChange(cam)

        return
      }

      event.preventDefault()
      const rect = canvas.getBoundingClientRect()
      const sx = event.clientX - rect.left
      const sy = event.clientY - rect.top
      const pinch = isPinchZoomWheel(event)
      const factor = pinch ? Math.exp(-event.deltaY * 0.01) : event.deltaY > 0 ? 0.92 : 1.08

      onCameraChange(zoomCameraAt(cameraRef.current, sx, sy, rect.width, rect.height, factor))
    }

    function onDblClick() {
      const rect = canvas.getBoundingClientRect()

      onCameraChange(
        fitCamera(
          nodesRef.current.map(node => ({ x: node.x, y: node.y })),
          rect.width,
          rect.height
        )
      )
    }

    canvas.addEventListener('pointerdown', onDown)
    canvas.addEventListener('pointermove', onMove)
    canvas.addEventListener('pointerup', onUp)
    canvas.addEventListener('pointercancel', onUp)
    canvas.addEventListener('wheel', onWheel, { passive: false })
    canvas.addEventListener('dblclick', onDblClick)

    return () => {
      cancelAnimationFrame(frame)
      scheduleRef.current = () => undefined
      sim.on('tick.draw', null)
      observer?.disconnect()
      canvas.removeEventListener('contextlost', onLost)
      canvas.removeEventListener('contextrestored', onRestored)
      canvas.removeEventListener('pointerdown', onDown)
      canvas.removeEventListener('pointermove', onMove)
      canvas.removeEventListener('pointerup', onUp)
      canvas.removeEventListener('pointercancel', onUp)
      canvas.removeEventListener('wheel', onWheel)
      canvas.removeEventListener('dblclick', onDblClick)
    }
  }, [onCameraChange, onSelect, sim, simAlphaTarget])

  useEffect(() => {
    scheduleRef.current()
  }, [camera, matchIds, neighborIds, palette, selectedId])

  return (
    <canvas
      aria-label={ariaLabel}
      className="absolute inset-0 block h-full w-full bg-transparent touch-none"
      ref={canvasRef}
    />
  )
}
