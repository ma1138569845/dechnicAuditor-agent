import { describe, expect, it } from 'vitest'

import { typeFill } from './graph-render'
import { GRAPH_LAYOUT_BOUND, createGraphSimulation, seedPosition } from './graph-sim'

describe('graph simulation seeds', () => {
  it('places the same id at a stable seed', () => {
    expect(seedPosition('e1')).toEqual(seedPosition('e1'))
    expect(seedPosition('e1')).not.toEqual(seedPosition('e2'))
  })

  it('resolves link endpoints to node objects after the first tick', () => {
    const { links, nodes, sim } = createGraphSimulation(
      [
        { description: '', id: 'a', name: 'A', type: 't' },
        { description: '', id: 'b', name: 'B', type: 't' }
      ],
      [{ description: '', id: 'l1', relation: 'x', source: 'a', target: 'b' }],
      () => 1
    )

    try {
      expect(nodes).toHaveLength(2)
      expect(typeof links[0].source).toBe('object')
      expect(typeof links[0].target).toBe('object')
    } finally {
      sim.stop()
    }
  })

  it('keeps node coordinates finite after many ticks', () => {
    const nodes = Array.from({ length: 40 }, (_, index) => ({
      description: '',
      id: `n${index}`,
      name: `N${index}`,
      type: 't'
    }))
    const links = Array.from({ length: 39 }, (_, index) => ({
      description: '',
      id: `l${index}`,
      relation: 'x',
      source: `n${index}`,
      target: `n${index + 1}`
    }))
    const { nodes: simNodes, sim } = createGraphSimulation(nodes, links, () => 2)

    try {
      sim.tick(80)
      for (const node of simNodes) {
        expect(Number.isFinite(node.x)).toBe(true)
        expect(Number.isFinite(node.y)).toBe(true)
        expect(Math.abs(node.x)).toBeLessThanOrEqual(GRAPH_LAYOUT_BOUND)
        expect(Math.abs(node.y)).toBeLessThanOrEqual(GRAPH_LAYOUT_BOUND)
      }
    } finally {
      sim.stop()
    }
  })
})

describe('typeFill', () => {
  it('is stable for a type and differs across types', () => {
    expect(typeFill('equipment', true)).toBe(typeFill('equipment', true))
    expect(typeFill('equipment', true)).not.toBe(typeFill('zone', true))
  })
})
