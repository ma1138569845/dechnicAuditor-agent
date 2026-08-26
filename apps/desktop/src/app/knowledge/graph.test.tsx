// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'
import { stubResizeObserver } from '@/test/jsdom'

const listEntities = vi.fn()
const listRelationships = vi.fn()

vi.mock('@/api/knowledge', async importOriginal => ({
  ...(await importOriginal<typeof import('@/api/knowledge')>()),
  listEntities: (...args: unknown[]) => listEntities(...args),
  listRelationships: (...args: unknown[]) => listRelationships(...args)
}))

stubResizeObserver()
HTMLCanvasElement.prototype.getContext = () => null

async function renderGraph() {
  const { GraphTab } = await import('./graph')
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } }
  })
  let result: ReturnType<typeof render>

  await act(async () => {
    result = render(
      <I18nProvider configClient={null} initialLocale="en">
        <QueryClientProvider client={client}>
          <GraphTab kbId="kb-1" />
        </QueryClientProvider>
      </I18nProvider>
    )
  })

  return result!
}

describe('GraphTab', () => {
  beforeEach(() => {
    listEntities.mockReset()
    listRelationships.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('keeps the empty state when there are no entities', async () => {
    listEntities.mockResolvedValue({ entities: [] })
    listRelationships.mockResolvedValue({ relationships: [] })

    await renderGraph()

    expect(await screen.findByText('No graph yet')).toBeTruthy()
    expect(listEntities).toHaveBeenCalledWith('kb-1', 500)
    expect(listRelationships).toHaveBeenCalledWith('kb-1', 2000)
  })

  it('renders a canvas graph with search, fit, and type filters', async () => {
    listEntities.mockResolvedValue({
      entities: [
        { description: 'Primary plant', id: 'e1', name: 'Chiller', type: 'equipment' },
        { description: '', id: 'e2', name: 'Roof', type: 'zone' }
      ]
    })
    listRelationships.mockResolvedValue({
      relationships: [{ description: 'serves', id: 'r1', relation: 'serves', source: 'Chiller', target: 'Roof' }]
    })

    await renderGraph()

    expect(await screen.findByPlaceholderText('Search entities…')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Fit' })).toBeTruthy()
    expect(screen.getByLabelText('Knowledge graph')).toBeTruthy()
    expect(screen.getByText('Select a node to see its connections.')).toBeTruthy()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'equipment' })).toBeTruthy()
    })
    expect(screen.getByRole('button', { name: 'zone' })).toBeTruthy()
    expect(screen.getByRole('separator', { name: 'Resize inspector' })).toBeTruthy()
  })
})

describe('clampInspectorWidth', () => {
  it('keeps the inspector readable without collapsing the canvas', async () => {
    const { clampInspectorWidth } = await import('./graph-layout')

    expect(clampInspectorWidth(320, 900)).toBe(320)
    expect(clampInspectorWidth(80, 900)).toBe(220)
    expect(clampInspectorWidth(800, 900)).toBe(560)
    expect(clampInspectorWidth(500, 500)).toBe(260)
  })
})
