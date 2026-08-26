import { describe, expect, it } from 'vitest'

import type { KnowledgeEntity, KnowledgeRelationship } from '@/api/knowledge'

import { buildKnowledgeGraph, neighborIds, nodeDegree, nodeRadiusForDegree } from './graph-model'

function entity(id: string, name: string, type = 'concept'): KnowledgeEntity {
  return { description: `${name} desc`, id, name, type }
}

function rel(id: string, source: string, target: string, relation = 'related'): KnowledgeRelationship {
  return { description: '', id, relation, source, target }
}

describe('buildKnowledgeGraph', () => {
  it('resolves relationship endpoints by entity id or name', () => {
    const model = buildKnowledgeGraph(
      [entity('e1', 'Chiller'), entity('e2', 'Cooling tower')],
      [rel('r1', 'e1', 'Cooling tower', 'feeds')]
    )

    expect(model.nodes.map(node => node.name)).toEqual(['Chiller', 'Cooling tower'])
    expect(model.links).toHaveLength(1)
    expect(model.links[0]).toMatchObject({ source: 'e1', target: 'e2', relation: 'feeds' })
  })

  it('drops self-loops, unknown endpoints, and duplicate edges', () => {
    const model = buildKnowledgeGraph(
      [entity('e1', 'Pump'), entity('e2', 'Valve')],
      [
        rel('r1', 'e1', 'e1'),
        rel('r2', 'e1', 'Missing'),
        rel('r3', 'e1', 'Valve', 'uses'),
        rel('r4', 'e1', 'Valve', 'uses')
      ]
    )

    expect(model.links).toHaveLength(1)
    expect(model.links[0]).toMatchObject({ source: 'e1', target: 'e2', relation: 'uses' })
  })

  it('collects sorted unique types', () => {
    const model = buildKnowledgeGraph([entity('a', 'A', 'zone'), entity('b', 'B', 'equipment')], [])

    expect(model.types).toEqual(['equipment', 'zone'])
  })
})

describe('graph neighborhood helpers', () => {
  it('counts degree and 1-hop neighbors including self', () => {
    const links = [
      { description: '', id: '1', relation: '', source: 'a', target: 'b' },
      { description: '', id: '2', relation: '', source: 'c', target: 'a' }
    ]

    expect(nodeDegree('a', links)).toBe(2)
    expect(nodeDegree('b', links)).toBe(1)
    expect([...neighborIds('a', links)].sort()).toEqual(['a', 'b', 'c'])
  })

  it('grows node radius with degree without jumping unbounded', () => {
    expect(nodeRadiusForDegree(0)).toBe(5)
    expect(nodeRadiusForDegree(4)).toBeGreaterThan(nodeRadiusForDegree(1))
    expect(nodeRadiusForDegree(10_000)).toBe(15)
  })
})
