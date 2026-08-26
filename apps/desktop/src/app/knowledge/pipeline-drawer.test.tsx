// @vitest-environment jsdom
import { QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { KnowledgeDocument } from '@/api/knowledge'
import { I18nProvider } from '@/i18n'
import { queryClient } from '@/lib/query-client'

const getKnowledgeDocument = vi.fn()
const listDocumentChunks = vi.fn()
const listVectorizationJobs = vi.fn()
const getDocumentPreview = vi.fn()
const getDocumentFilePayload = vi.fn()

vi.mock('@/api/knowledge', async importOriginal => ({
  ...(await importOriginal<typeof import('@/api/knowledge')>()),
  getKnowledgeDocument: (...args: unknown[]) => getKnowledgeDocument(...args),
  listDocumentChunks: (...args: unknown[]) => listDocumentChunks(...args),
  listVectorizationJobs: (...args: unknown[]) => listVectorizationJobs(...args),
  getDocumentPreview: (...args: unknown[]) => getDocumentPreview(...args),
  getDocumentFilePayload: (...args: unknown[]) => getDocumentFilePayload(...args)
}))

vi.mock('@/components/chat/compact-markdown', () => ({
  CompactMarkdown: ({ text }: { text: string }) => <div>{text}</div>
}))

vi.mock('@/app/chat/right-rail/preview-file', () => ({
  MarkdownPreview: ({ text }: { text: string }) => <div data-testid="md-preview">{text}</div>
}))

vi.mock('@/components/chat/office-preview', () => ({
  OfficePreview: ({ officeKind }: { officeKind: string }) => <div data-testid="office-preview">{officeKind}</div>
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

function doc(overrides: Partial<KnowledgeDocument> = {}): KnowledgeDocument {
  return {
    chunk_count: 2,
    created_at: '2026-01-15T00:00:00Z',
    error_message: null,
    file_name: 'hospital-audit.pdf',
    file_path: '/tmp/hospital-audit.pdf',
    file_size: 4_900_000,
    file_type: 'pdf',
    folder_id: null,
    id: 'doc-1',
    kb_id: 'kb-1',
    parse_status: 'completed',
    summary_status: 'completed',
    summary_text: 'Hospital energy use is moderate.',
    title: 'Audit',
    updated_at: '2026-01-15T00:00:00Z',
    vector_count: 2,
    ...overrides
  }
}

async function renderInspector(document = doc()) {
  getKnowledgeDocument.mockResolvedValue(document)

  const { KnowledgePipelineDrawer } = await import('./pipeline-drawer')

  return render(
    <I18nProvider configClient={null} initialLocale="en">
      <QueryClientProvider client={queryClient}>
        <KnowledgePipelineDrawer doc={document} kbId="kb-1" onClose={vi.fn()} />
      </QueryClientProvider>
    </I18nProvider>
  )
}

beforeEach(() => {
  getKnowledgeDocument.mockResolvedValue(doc())
  listDocumentChunks.mockResolvedValue({
    chunks: [
      {
        char_count: 40,
        chunk_index: 0,
        chunk_type: 'text',
        content: '# Chapter 1\nSummary of the audit.',
        id: 'c1',
        is_enabled: true,
        metadata: {}
      }
    ]
  })
  listVectorizationJobs.mockResolvedValue({ jobs: [] })
  getDocumentPreview.mockResolvedValue({
    content: 'extracted pdf text',
    file_name: 'hospital-audit.pdf',
    id: 'doc-1',
    lines: 12,
    path: '/tmp/hospital-audit.pdf',
    size: 100,
    summary: ''
  })
  getDocumentFilePayload.mockResolvedValue({
    data: btoa('%PDF-1.4 mock'),
    filename: 'hospital-audit.pdf',
    kind: 'pdf',
    mime: 'application/pdf',
    size: 20,
    too_large: false
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  queryClient.clear()
})

describe('KnowledgePipelineDrawer', () => {
  it('opens on the preview tab with generate actions in the more menu', async () => {
    await renderInspector()

    expect(await screen.findByRole('heading', { name: 'hospital-audit.pdf' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Preview' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Summary' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Chunks' })).toBeTruthy()
    await waitFor(() => {
      expect(document.querySelector('iframe[title="hospital-audit.pdf"]')).toBeTruthy()
    })

    fireEvent.keyDown(screen.getByRole('button', { name: 'More actions' }), { key: 'Enter' })

    expect(await screen.findByRole('menuitem', { name: 'Re-vectorize' })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Generate summary' })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Generate wiki' })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Build graph' })).toBeTruthy()
    expect(screen.queryByRole('menuitem', { name: 'Wiki only' })).toBeNull()
  })

  it('shows the summary pane when that tab is selected', async () => {
    await renderInspector()
    await screen.findByRole('heading', { name: 'hospital-audit.pdf' })

    fireEvent.click(screen.getByRole('button', { name: 'Summary' }))

    expect(await screen.findByText('Hospital energy use is moderate.')).toBeTruthy()
  })

  it('opens wiki confirm from the more menu without a nested wiki-only choice', async () => {
    await renderInspector()
    await screen.findByRole('heading', { name: 'hospital-audit.pdf' })

    fireEvent.keyDown(screen.getByRole('button', { name: 'More actions' }), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Generate wiki' }))

    expect(await screen.findByText('Curate after generating')).toBeTruthy()
    expect(screen.queryByText('Wiki only')).toBeNull()
  })

  it('renders markdown with the document preview, not a plain text dump', async () => {
    getDocumentPreview.mockResolvedValue({
      content: '# Energy audit\n\nHospital HVAC load.',
      file_name: 'notes.md',
      id: 'doc-md',
      lines: 3,
      path: '/tmp/notes.md',
      size: 40,
      summary: ''
    })

    await renderInspector(doc({ file_name: 'notes.md', file_type: 'md', id: 'doc-md' }))

    expect((await screen.findByTestId('md-preview')).textContent).toContain('Energy audit')
    expect(document.querySelector('iframe')).toBeNull()
    expect(screen.queryByTestId('office-preview')).toBeNull()
  })

  it('renders office files through OfficePreview from the file payload', async () => {
    getDocumentFilePayload.mockResolvedValue({
      data: btoa('PK mock docx'),
      filename: 'memo.docx',
      kind: 'binary',
      mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      size: 12,
      too_large: false
    })

    await renderInspector(doc({ file_name: 'memo.docx', file_type: 'docx', id: 'doc-docx' }))

    expect((await screen.findByTestId('office-preview')).textContent).toContain('docx')
    expect(getDocumentFilePayload).toHaveBeenCalled()
  })
})
