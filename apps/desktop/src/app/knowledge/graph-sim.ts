import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation
} from 'd3-force'

import { clamp } from './graph-camera'
import { nodeRadiusForDegree, type GraphLink, type GraphNode } from './graph-model'

export interface SimNode extends GraphNode {
  fx?: null | number
  fy?: null | number
  index?: number
  radius: number
  vx: number
  vy: number
  x: number
  y: number
}

export interface SimLink {
  description: string
  id: string
  index?: number
  relation: string
  source: SimNode | string
  target: SimNode | string
}

export const GRAPH_LAYOUT_BOUND = 2400

export function seedPosition(id: string): { x: number; y: number } {
  let hash = 2166136261

  for (let index = 0; index < id.length; index += 1) {
    hash ^= id.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }

  const angle = ((hash >>> 0) % 3600) / 3600 * Math.PI * 2
  const radius = 40 + ((hash >>> 8) % 220)

  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius }
}

export function clampSimNodes(nodes: SimNode[], bound = GRAPH_LAYOUT_BOUND): void {
  for (const node of nodes) {
    if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) {
      const seed = seedPosition(node.id)

      node.x = seed.x
      node.y = seed.y
      node.vx = 0
      node.vy = 0
      continue
    }

    node.x = clamp(node.x, -bound, bound)
    node.y = clamp(node.y, -bound, bound)
    node.vx = Number.isFinite(node.vx) ? clamp(node.vx, -40, 40) : 0
    node.vy = Number.isFinite(node.vy) ? clamp(node.vy, -40, 40) : 0
  }
}

export function createGraphSimulation(
  nodes: GraphNode[],
  links: GraphLink[],
  degree: (id: string) => number
): { links: SimLink[]; nodes: SimNode[]; sim: Simulation<SimNode, SimLink> } {
  const simNodes: SimNode[] = nodes.map(node => {
    const seed = seedPosition(node.id)

    return {
      ...node,
      radius: nodeRadiusForDegree(degree(node.id)),
      vx: 0,
      vy: 0,
      x: seed.x,
      y: seed.y
    }
  })

  const simLinks: SimLink[] = links.map(link => ({
    description: link.description,
    id: link.id,
    relation: link.relation,
    source: link.source,
    target: link.target
  }))

  const count = Math.max(1, simNodes.length)
  const charge = -Math.max(28, 1600 / Math.sqrt(count))

  const sim = forceSimulation(simNodes)
    .force(
      'link',
      forceLink<SimNode, SimLink>(simLinks)
        .id(node => node.id)
        .distance(count > 200 ? 52 : 76)
        .strength(0.4)
    )
    .force(
      'charge',
      forceManyBody<SimNode>()
        .strength(charge)
        .distanceMax(320)
    )
    .force('center', forceCenter(0, 0).strength(0.06))
    .force('x', forceX(0).strength(0.03))
    .force('y', forceY(0).strength(0.03))
    .force(
      'collide',
      forceCollide<SimNode>()
        .radius(node => node.radius + (count > 200 ? 4 : 8))
        .strength(count > 200 ? 0.4 : 0.7)
    )
    .alpha(1)
    .alphaDecay(count > 200 ? 0.04 : 0.022)
    .velocityDecay(0.42)

  sim.on('tick.clamp', () => clampSimNodes(simNodes))
  sim.tick()
  clampSimNodes(simNodes)

  return { links: simLinks, nodes: simNodes, sim }
}
