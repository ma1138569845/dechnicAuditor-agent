// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { KnowledgeBase } from '@/api/knowledge'
import { I18nProvider } from '@/i18n'

const listKnowledgeBases = vi.fn()
const createKnowledgeBase = vi.fn()
const deleteKnowledgeBase = vi.fn()
const getKnowledgeBase = vi.fn()
const getKnowledgeStats = vi.fn()
const listVectorizationJobs = vi.fn()
const listCurationJobs = vi.fn()
const listAllKnowledgeFolders = vi.fn()
const listKnowledgeDocuments = vi.fn()
const listKnowledgeWiki = vi.fn()
const listEntities = vi.fn()
const listRelationships = vi.fn()
const searchKnowledgeBase = vi.fn()

vi.mock('@/api/knowledge', async importOriginal => ({
  ...(await importOriginal<typeof import('@/api/knowledge')>()),
  listKnowledgeBases: () => listKnowledgeBases(),
  createKnowledgeBase: (name: string, description?: string) => createKnowledgeBase(name, description),
  deleteKnowledgeBase: (id: string) => deleteKnowledgeBase(id),
  getKnowledgeBase: (id: string) => getKnowledgeBase(id),
  getKnowledgeStats: (id: string) => getKnowledgeStats(id),
  listVectorizationJobs: (id: string) => listVectorizationJobs(id),
  listCurationJobs: (id: string) => listCurationJobs(id),
  listAllKnowledgeFolders: (id: string) => listAllKnowledgeFolders(id),
  listKnowledgeDocuments: (...args: unknown[]) => listKnowledgeDocuments(...args),
  listKnowledgeWiki: (...args: unknown[]) => listKnowledgeWiki(...args),
  listEntities: (...args: unknown[]) => listEntities(...args),
  listRelationships: (...args: unknown[]) => listRelationships(...args),
  searchKnowledgeBase: (...args: unknown[]) => searchKnowledgeBase(...args)
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

function kb(overrides: Partial<KnowledgeBase> = {}): KnowledgeBase {
  return {
    created_at: '2026-01-15T00:00:00Z',
    description: 'Audit corpus',
    embedding_model: 'dashscope/text-embedding-v3',
    id: 'kb-1',
    is_system: false,
    kb_type: 'energy_audit',
    name: 'Energy reports',
    qdrant_collection: 'energy_reports',
    root_path: '/tmp/kb-1',
    stats: {
      completed: 3,
      failed: 0,
      orphaned: 0,
      processing: 0,
      total_documents: 3,
      total_size: 4096
    },
    updated_at: '2026-01-15T00:00:00Z',
    ...overrides
  }
}

async function renderView(path = '/knowledge') {
  const { KnowledgeView } = await import('./index')
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } }
  })

  return render(
    <I18nProvider configClient={null} initialLocale="en">
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route element={<KnowledgeView />} path="/knowledge/:kbId" />
            <Route element={<KnowledgeView />} path="/knowledge" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nProvider>
  )
}

beforeEach(() => {
  listKnowledgeBases.mockResolvedValue({
    bases: [
      kb({ id: 'sys', is_system: true, name: 'System corpus' }),
      kb({ id: 'mine', is_system: false, name: 'My notes' })
    ]
  })
  createKnowledgeBase.mockResolvedValue(kb({ id: 'new', name: 'Fresh' }))
  deleteKnowledgeBase.mockResolvedValue({ deleted: true })
  getKnowledgeBase.mockResolvedValue(kb())
  getKnowledgeStats.mockResolvedValue(kb().stats)
  listVectorizationJobs.mockResolvedValue({ jobs: [] })
  listCurationJobs.mockResolvedValue({ jobs: [] })
  listAllKnowledgeFolders.mockResolvedValue([])
  listKnowledgeDocuments.mockResolvedValue({ documents: [], page: 1, page_size: 50, total: 0 })
  listKnowledgeWiki.mockResolvedValue({ pages: [] })
  listEntities.mockResolvedValue({ entities: [] })
  listRelationships.mockResolvedValue({ relationships: [] })
  searchKnowledgeBase.mockResolvedValue({ results: [] })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('KnowledgeView list', () => {
  it('shows system and user knowledge bases', { timeout: 20_000 }, async () => {
    await renderView()

    expect(await screen.findByText('System corpus')).toBeTruthy()
    expect(screen.getByText('My notes')).toBeTruthy()
    expect(screen.getByText('System knowledge bases')).toBeTruthy()
  })

  it('opens the create dialog from the header action', async () => {
    await renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'New knowledge base' }))

    expect(await screen.findByRole('heading', { name: 'Create knowledge base' })).toBeTruthy()
    fireEvent.change(screen.getByPlaceholderText('Energy-audit reports'), { target: { value: 'Fresh' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    await waitFor(() => {
      expect(createKnowledgeBase).toHaveBeenCalledWith('Fresh', '')
    })
  })
})

describe('KnowledgeView detail', () => {
  it('shows migrated tabs and generate/rebuild actions', async () => {
    await renderView('/knowledge/kb-1')

    expect(await screen.findByText('Energy reports')).toBeTruthy()
    expect(screen.getAllByText('Documents').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Search').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Wiki').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Graph').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Jobs').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Stats').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /Generate/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Rebuild' })).toBeTruthy()
  })

  it('opens search, wiki, graph, jobs, and stats tabs', async () => {
    await renderView('/knowledge/kb-1')
    await screen.findByText('Energy reports')

    fireEvent.click(screen.getAllByRole('button', { name: 'Search' })[0])
    expect(await screen.findByPlaceholderText('Search this knowledge base…')).toBeTruthy()

    fireEvent.click(screen.getAllByRole('button', { name: 'Wiki' })[0])
    expect(await screen.findByText('No wiki pages')).toBeTruthy()

    fireEvent.click(screen.getAllByRole('button', { name: 'Graph' })[0])
    expect(await screen.findByText('No graph yet')).toBeTruthy()

    fireEvent.click(screen.getAllByRole('button', { name: 'Jobs' })[0])
    expect(await screen.findByText('No jobs')).toBeTruthy()

    fireEvent.click(screen.getAllByRole('button', { name: 'Stats' })[0])
    expect(await screen.findByText('Total size')).toBeTruthy()
  })
})
