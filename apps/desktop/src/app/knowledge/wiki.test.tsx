// @vitest-environment jsdom
import { QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { WikiPage } from '@/api/knowledge'
import { I18nProvider } from '@/i18n'
import { queryClient } from '@/lib/query-client'

const listKnowledgeWiki = vi.fn()
const getWikiPage = vi.fn()
const updateWikiReview = vi.fn()
const evaluateWikiQuality = vi.fn()

vi.mock('@/api/knowledge', async importOriginal => ({
  ...(await importOriginal<typeof import('@/api/knowledge')>()),
  listKnowledgeWiki: (...args: unknown[]) => listKnowledgeWiki(...args),
  getWikiPage: (...args: unknown[]) => getWikiPage(...args),
  updateWikiReview: (...args: unknown[]) => updateWikiReview(...args),
  evaluateWikiQuality: (...args: unknown[]) => evaluateWikiQuality(...args)
}))

vi.mock('@/app/chat/right-rail/preview-file', () => ({
  MarkdownPreview: ({ text }: { text: string }) => <div data-testid="wiki-article">{text}</div>
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

function page(overrides: Partial<WikiPage> = {}): WikiPage {
  return {
    content: ['岚山区巨峰中心卫生院能源审计报告', '', '一、 审计范围与方法', '本次能源审计依据相关标准。'].join('\n'),
    id: 'wiki-1',
    review_status: 'pending',
    source: 'doc',
    title: '岚山区巨峰中心卫生院能源审计报告',
    updated_at: '2024-08-26T00:00:00Z',
    ...overrides
  }
}

async function renderWiki() {
  const { WikiTab } = await import('./wiki')

  return render(
    <I18nProvider configClient={null} initialLocale="en">
      <QueryClientProvider client={queryClient}>
        <WikiTab kbId="kb-1" />
      </QueryClientProvider>
    </I18nProvider>
  )
}

beforeEach(() => {
  listKnowledgeWiki.mockResolvedValue({ pages: [page()] })
  getWikiPage.mockResolvedValue(page())
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  queryClient.clear()
})

describe('WikiTab', () => {
  it('opens an in-page article with document markdown, not a sheet overlay', async () => {
    await renderWiki()

    fireEvent.click(await screen.findByRole('button', { name: /岚山区巨峰中心卫生院能源审计报告/ }))

    expect(await screen.findByTestId('wiki-article')).toBeTruthy()
    expect(screen.getByTestId('wiki-article').textContent).toContain('## 一、 审计范围与方法')
    expect(screen.getByRole('button', { name: 'Approve' })).toBeTruthy()
    expect(screen.getAllByText('Pending').length).toBeGreaterThan(0)
    expect(document.querySelector('[data-slot="sheet-overlay"]')).toBeNull()
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull()
  })
})
