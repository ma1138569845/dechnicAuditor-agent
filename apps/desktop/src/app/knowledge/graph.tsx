import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'

import { listEntities, listRelationships, type KnowledgeEntity } from '@/api/knowledge'
import { PageLoader } from '@/components/page-loader'
import { Button } from '@/components/ui/button'
import { SearchField } from '@/components/ui/search-field'
import { useThemeEpoch } from '@/hooks/use-theme-epoch'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'

import { PanelEmpty } from '../overlays/panel'

import { fitCamera, type GraphCamera } from './graph-camera'
import { GraphCanvas } from './graph-canvas'
import {
  clampInspectorWidth,
  INSPECTOR_DEFAULT_PX,
  INSPECTOR_MAX_PX,
  INSPECTOR_MIN_PX
} from './graph-layout'
import { buildKnowledgeGraph, neighborIds, nodeDegree, type GraphLink } from './graph-model'
import { resolveCssColor, type GraphPalette } from './graph-render'
import { createGraphSimulation, type SimLink, type SimNode } from './graph-sim'
import { knowledgeKeys } from './keys'

const ENTITY_LIMIT = 500
const RELATION_LIMIT = 2000

const lightFallback: GraphPalette = {
  accent: 'rgb(82, 82, 91)',
  bg: 'rgb(250, 250, 252)',
  dark: false,
  muted: 'rgb(113, 113, 122)',
  node: 'rgb(82, 82, 91)',
  stroke: 'rgb(161, 161, 170)',
  text: 'rgb(24, 24, 27)'
}

const darkFallback: GraphPalette = {
  accent: 'rgb(148, 163, 184)',
  bg: 'rgb(18, 18, 20)',
  dark: true,
  muted: 'rgb(148, 163, 184)',
  node: 'rgb(148, 163, 184)',
  stroke: 'rgb(100, 116, 139)',
  text: 'rgb(226, 232, 240)'
}

function fallbackPalette(dark: boolean): GraphPalette {
  return dark ? darkFallback : lightFallback
}

export function GraphTab({ kbId }: { kbId: string }) {
  const { t } = useI18n()
  const k = t.knowledge
  const themeEpoch = useThemeEpoch()
  const wrapRef = useRef<HTMLDivElement>(null)
  const splitRef = useRef<HTMLDivElement>(null)
  const simRef = useRef<ReturnType<typeof createGraphSimulation> | null>(null)
  const fittedRef = useRef(false)

  const [query, setQuery] = useState('')
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set())
  const [selectedId, setSelectedId] = useState<null | string>(null)
  const [inspectorWidth, setInspectorWidth] = useState(INSPECTOR_DEFAULT_PX)
  const [draggingSplit, setDraggingSplit] = useState(false)
  const [camera, setCamera] = useState<GraphCamera>({ k: 1, x: 0, y: 0 })
  const [bundle, setBundle] = useState<{
    links: SimLink[]
    nodes: SimNode[]
    sim: ReturnType<typeof createGraphSimulation>['sim']
  } | null>(null)
  const [palette, setPalette] = useState<GraphPalette>(lightFallback)

  const entitiesQuery = useQuery({
    queryFn: () => listEntities(kbId, ENTITY_LIMIT),
    queryKey: knowledgeKeys.entities(kbId)
  })
  const relationshipsQuery = useQuery({
    queryFn: () => listRelationships(kbId, RELATION_LIMIT),
    queryKey: knowledgeKeys.relationships(kbId)
  })

  const entities = entitiesQuery.data?.entities ?? []
  const relationships = relationshipsQuery.data?.relationships ?? []
  const model = useMemo(() => buildKnowledgeGraph(entities, relationships), [entities, relationships])

  const visible = useMemo(() => {
    const nodes = model.nodes.filter(node => !hiddenTypes.has(node.type))
    const ids = new Set(nodes.map(node => node.id))
    const links = model.links.filter(link => ids.has(link.source) && ids.has(link.target))

    return { links, nodes }
  }, [hiddenTypes, model])

  const graphKey = useMemo(
    () => `${visible.nodes.map(node => node.id).join(',')}|${visible.links.map(link => link.id).join(',')}`,
    [visible]
  )
  const visibleRef = useRef(visible)

  visibleRef.current = visible

  useEffect(() => {
    const snapshot = visibleRef.current

    if (snapshot.nodes.length === 0) {
      simRef.current?.sim.stop()
      simRef.current = null
      setBundle(null)

      return
    }

    const degree = (id: string) => nodeDegree(id, snapshot.links)
    const next = createGraphSimulation(snapshot.nodes, snapshot.links, degree)

    simRef.current?.sim.stop()
    simRef.current = next
    fittedRef.current = false
    setBundle({ links: next.links, nodes: next.nodes, sim: next.sim })

    let cancelled = false

    next.sim.on('tick.fit', () => {
      if (cancelled || fittedRef.current || next.sim.alpha() > 0.4) {
        return
      }

      const rect = wrapRef.current?.getBoundingClientRect()

      if (!rect || rect.width < 8 || rect.height < 8) {
        return
      }

      fittedRef.current = true
      setCamera(fitCamera(next.nodes, rect.width, rect.height))
    })

    return () => {
      cancelled = true
      next.sim.stop()
      next.sim.on('tick.fit', null)
    }
  }, [graphKey])

  useEffect(() => {
    const root = wrapRef.current

    if (!root) {
      return
    }

    setPalette(readPalette(root))
  }, [model.nodes.length, themeEpoch])

  useEffect(() => {
    const split = splitRef.current

    if (!split) {
      return
    }

    const observer = new ResizeObserver(() => {
      setInspectorWidth(width => clampInspectorWidth(width, split.getBoundingClientRect().width))
    })

    observer.observe(split)

    return () => observer.disconnect()
  }, [model.nodes.length])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setSelectedId(null)
      }
    }

    window.addEventListener('keydown', onKey)

    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (selectedId && !visible.nodes.some(node => node.id === selectedId)) {
      setSelectedId(null)
    }
  }, [selectedId, visible.nodes])

  const matchIds = useMemo(() => {
    const needle = query.trim().toLowerCase()

    if (!needle) {
      return null
    }

    return new Set(
      (bundle?.nodes ?? [])
        .filter(node => `${node.name} ${node.type}`.toLowerCase().includes(needle))
        .map(node => node.id)
    )
  }, [bundle, query])

  const selectedNeighbors = useMemo(
    () => (selectedId ? neighborIds(selectedId, visible.links) : null),
    [selectedId, visible.links]
  )

  const selected = bundle?.nodes.find(node => node.id === selectedId) ?? null
  const selectedLinks = useMemo(
    () => (selectedId ? visible.links.filter(link => link.source === selectedId || link.target === selectedId) : []),
    [selectedId, visible.links]
  )

  const simAlphaTarget = useCallback((value: number) => {
    const sim = simRef.current?.sim

    if (!sim) {
      return
    }

    sim.alphaTarget(value).restart()
  }, [])

  const handleFit = useCallback(() => {
    const rect = wrapRef.current?.getBoundingClientRect()
    const nodes = simRef.current?.nodes ?? []

    if (!rect) {
      return
    }

    setCamera(fitCamera(nodes, rect.width, rect.height))
  }, [])

  const startInspectorDrag = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const split = splitRef.current

    if (!split || event.button !== 0) {
      return
    }

    event.preventDefault()
    const startX = event.clientX
    const startWidth = inspectorWidth
    const maxSplit = split.getBoundingClientRect().width

    setDraggingSplit(true)

    const onMove = (move: PointerEvent) => {
      setInspectorWidth(clampInspectorWidth(startWidth - (move.clientX - startX), maxSplit))
    }

    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      setDraggingSplit(false)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp, { once: true })
  }, [inspectorWidth])

  if ((entitiesQuery.isPending && !entitiesQuery.data) || (relationshipsQuery.isPending && !relationshipsQuery.data)) {
    return <PageLoader label={t.common.loading} />
  }

  if (model.nodes.length === 0) {
    return <PanelEmpty description={k.noGraphDesc} icon="search" title={k.noGraphTitle} />
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-3 px-6 py-2">
        <SearchField
          containerClassName="min-w-[10rem] flex-1"
          onChange={setQuery}
          placeholder={k.graphSearch}
          value={query}
        />
        <span className="text-[0.7rem] text-muted-foreground">
          {k.entities} {visible.nodes.length} · {k.relationships} {visible.links.length}
        </span>
        <Button onClick={handleFit} size="xs" variant="ghost">
          {k.graphFit}
        </Button>
      </div>
      {model.types.length > 1 ? (
        <div className="flex max-h-20 shrink-0 flex-wrap gap-1 overflow-y-auto px-6 pb-2">
          {model.types.map(type => {
            const hidden = hiddenTypes.has(type)

            return (
              <Button
                className={cn(hidden && 'opacity-40')}
                key={type}
                onClick={() => {
                  setHiddenTypes(prev => {
                    const next = new Set(prev)

                    if (next.has(type)) {
                      next.delete(type)
                    } else {
                      next.add(type)
                    }

                    return next
                  })
                }}
                size="xs"
                variant="ghost"
              >
                {type}
              </Button>
            )
          })}
        </div>
      ) : null}

      <div className={cn('flex min-h-0 min-w-0 flex-1', draggingSplit && 'select-none')} ref={splitRef}>
        <div className="relative min-h-0 min-w-0 flex-1" ref={wrapRef}>
          {bundle ? (
            <GraphCanvas
              ariaLabel={k.graphCanvas}
              camera={camera}
              links={bundle.links}
              matchIds={matchIds}
              neighborIds={selectedNeighbors}
              nodes={bundle.nodes}
              onCameraChange={setCamera}
              onSelect={setSelectedId}
              palette={palette}
              selectedId={selectedId}
              sim={bundle.sim}
              simAlphaTarget={simAlphaTarget}
            />
          ) : null}
          <p className="pointer-events-none absolute bottom-3 left-4 text-[0.65rem] text-muted-foreground">
            {k.graphHint}
          </p>
        </div>

        <aside className="relative flex shrink-0 flex-col overflow-y-auto px-4 py-4" style={{ width: inspectorWidth }}>
          <div
            aria-label={k.graphResize}
            aria-orientation="vertical"
            aria-valuemax={INSPECTOR_MAX_PX}
            aria-valuemin={INSPECTOR_MIN_PX}
            aria-valuenow={inspectorWidth}
            className="group/vsash absolute inset-y-0 left-0 z-10 w-1.5 -translate-x-1/2 cursor-col-resize touch-none"
            onDoubleClick={() => setInspectorWidth(INSPECTOR_DEFAULT_PX)}
            onPointerDown={startInspectorDrag}
            role="separator"
          >
            <div
              className={cn(
                'absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-colors',
                draggingSplit
                  ? 'bg-(--ui-stroke-secondary)'
                  : 'bg-(--ui-stroke-tertiary) group-hover/vsash:bg-(--ui-stroke-secondary)'
              )}
            />
          </div>
          {selected ? (
            <GraphInspector
              entityById={Object.fromEntries(entities.map(entity => [entity.id, entity]))}
              links={selectedLinks}
              nameById={Object.fromEntries(model.nodes.map(node => [node.id, node.name]))}
              node={selected}
              onSelect={setSelectedId}
            />
          ) : (
            <p className="text-xs text-muted-foreground">{k.graphNoSelection}</p>
          )}
        </aside>
      </div>
    </div>
  )
}

function GraphInspector({
  entityById,
  links,
  nameById,
  node,
  onSelect
}: {
  entityById: Record<string, KnowledgeEntity>
  links: GraphLink[]
  nameById: Record<string, string>
  node: SimNode
  onSelect: (id: string) => void
}) {
  const { t } = useI18n()
  const k = t.knowledge
  const entity = entityById[node.id]

  return (
    <div className="flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-semibold leading-snug">{node.name}</h2>
        <p className="mt-0.5 text-[0.7rem] text-muted-foreground">{node.type}</p>
      </div>
      {entity?.description || node.description ? (
        <p className="text-xs leading-relaxed text-foreground/90">{entity?.description || node.description}</p>
      ) : null}
      <div>
        <h3 className="mb-1.5 text-[0.65rem] font-medium uppercase tracking-wider text-muted-foreground">
          {k.graphNeighbors} ({links.length})
        </h3>
        {links.length === 0 ? (
          <p className="text-xs text-muted-foreground">{k.graphOrphan}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {links.map(link => {
              const other = link.source === node.id ? link.target : link.source
              const otherName = nameById[other] || entityById[other]?.name || other
              const inbound = link.target === node.id

              return (
                <li className="text-xs leading-relaxed" key={link.id}>
                  <span className="text-muted-foreground">{inbound ? '←' : '→'}</span>
                  {link.relation ? <span className="text-muted-foreground"> {link.relation} </span> : ' '}
                  <Button onClick={() => onSelect(other)} size="inline" variant="textStrong">
                    {otherName}
                  </Button>
                  {link.description ? <p className="mt-0.5 text-muted-foreground">{link.description}</p> : null}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

function isDarkTheme(el: HTMLElement): boolean {
  return el.ownerDocument.documentElement.classList.contains('dark')
}

function readPalette(el: HTMLElement): GraphPalette {
  const dark = isDarkTheme(el)
  const fallback = fallbackPalette(dark)
  const styles = getComputedStyle(el)

  function token(name: string, fallbackColor: string): string {
    const raw = styles.getPropertyValue(name).trim()

    return resolveCssColor(raw || `var(${name})`, fallbackColor)
  }

  function opaque(names: string[], fallbackColor: string): string {
    for (const name of names) {
      const raw = styles.getPropertyValue(name).trim()
      const resolved = resolveCssColor(raw || `var(${name})`, '')

      if (resolved) {
        return resolved
      }
    }

    return fallbackColor
  }

  return {
    accent: token('--ui-accent', fallback.accent),
    bg: opaque(['--ui-bg-chrome', '--background', '--dt-background'], fallback.bg),
    dark,
    muted: token('--ui-text-tertiary', fallback.muted),
    node: token('--ui-accent', fallback.node),
    stroke: token('--ui-stroke-secondary', fallback.stroke),
    text: token('--ui-text-primary', fallback.text)
  }
}
