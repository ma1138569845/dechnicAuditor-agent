import type { KnowledgeEntity, KnowledgeRelationship } from '@/api/knowledge'

export interface GraphNode {
  description: string
  id: string
  name: string
  type: string
}

export interface GraphLink {
  description: string
  id: string
  relation: string
  source: string
  target: string
}

export interface KnowledgeGraphModel {
  links: GraphLink[]
  nodes: GraphNode[]
  types: string[]
}

export function buildKnowledgeGraph(
  entities: KnowledgeEntity[],
  relationships: KnowledgeRelationship[]
): KnowledgeGraphModel {
  const nodes: GraphNode[] = []
  const byName = new Map<string, GraphNode>()
  const byId = new Map<string, GraphNode>()

  for (const entity of entities) {
    const name = entity.name?.trim()

    if (!name) {
      continue
    }

    const node: GraphNode = {
      description: entity.description ?? '',
      id: entity.id,
      name,
      type: (entity.type || 'entity').trim() || 'entity'
    }

    nodes.push(node)
    byId.set(node.id, node)
    byName.set(name.toLowerCase(), node)
  }

  const links: GraphLink[] = []
  const seen = new Set<string>()

  for (const rel of relationships) {
    const source = resolveEndpoint(rel.source, byId, byName)
    const target = resolveEndpoint(rel.target, byId, byName)

    if (!source || !target || source.id === target.id) {
      continue
    }

    const key = `${source.id}\0${rel.relation || ''}\0${target.id}`

    if (seen.has(key)) {
      continue
    }

    seen.add(key)
    links.push({
      description: rel.description ?? '',
      id: rel.id || key,
      relation: rel.relation || '',
      source: source.id,
      target: target.id
    })
  }

  const types = [...new Set(nodes.map(node => node.type))].sort((a, b) => a.localeCompare(b))

  return { links, nodes, types }
}

export function nodeDegree(nodeId: string, links: GraphLink[]): number {
  let count = 0

  for (const link of links) {
    if (link.source === nodeId || link.target === nodeId) {
      count += 1
    }
  }

  return count
}

export function neighborIds(nodeId: string, links: GraphLink[]): Set<string> {
  const next = new Set<string>([nodeId])

  for (const link of links) {
    if (link.source === nodeId) {
      next.add(link.target)
    }

    if (link.target === nodeId) {
      next.add(link.source)
    }
  }

  return next
}

export function nodeRadiusForDegree(degree: number): number {
  return 5 + Math.min(10, Math.sqrt(Math.max(0, degree)) * 2.2)
}

function resolveEndpoint(
  value: string,
  byId: Map<string, GraphNode>,
  byName: Map<string, GraphNode>
): GraphNode | undefined {
  const trimmed = value?.trim()

  if (!trimmed) {
    return undefined
  }

  return byId.get(trimmed) ?? byName.get(trimmed.toLowerCase())
}
