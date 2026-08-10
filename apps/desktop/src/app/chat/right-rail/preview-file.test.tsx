import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'
import { readDesktopFileDataUrl, readDesktopFileText } from '@/lib/desktop-fs'

import { LocalFilePreview } from './preview-file'

// `submitAiEdit` dispatches composer mutations through window CustomEvents
// (composer/focus.ts) — the test listens on the bus instead of mocking the
// module, so the assertions prove the real handoff path end to end.
const COMPOSER_INSERT_REFS = 'hermes:composer-insert-refs'
const COMPOSER_INSERT = 'hermes:composer-insert'

vi.mock('@/lib/desktop-fs', () => ({
  desktopFileDiff: vi.fn(async () => ''),
  desktopFsCacheKey: vi.fn(() => 'test-cache-key'),
  desktopGitRoot: vi.fn(async () => null),
  readDesktopFileDataUrl: vi.fn(async () => ''),
  readDesktopFileText: vi.fn(async () => ({
    binary: false,
    byteSize: 42,
    path: 'C:/repo/notes.txt',
    text: 'first line\nsecond line\nthird line'
  })),
  writeDesktopFileText: vi.fn(async () => ({ path: 'C:/repo/notes.txt' }))
}))

vi.mock('mammoth', () => ({
  default: {
    convertToHtml: vi.fn()
  }
}))

const slot = (container: HTMLElement, name: string) => container.querySelector(`[data-slot="${name}"]`)

// The load is async PAST the mocked read — `readTextPreview` wraps it and the
// component only lands `state.text` (which gates the read view) a few awaits
// later. Waiting on the mock alone can catch the component mid-load, so each
// test waits for the actual DOM element it drives instead.
async function waitForEl(container: HTMLElement, selector: string): Promise<HTMLElement> {
  await waitFor(() => {
    expect(container.querySelector(selector)).toBeTruthy()
  })

  return container.querySelector(selector) as HTMLElement
}

function renderPreview({
  language = 'text',
  officeKind,
  path = 'C:/repo/notes.txt',
  previewKind = 'text'
}: {
  language?: string
  officeKind?: 'docx' | 'xlsx' | 'pptx'
  path?: string
  previewKind?: 'binary' | 'html' | 'image' | 'office' | 'text'
} = {}) {
  const rendered = render(
    <I18nProvider configClient={null}>
      <LocalFilePreview
        reloadKey={0}
        target={{
          kind: 'file',
          label: 'notes.txt',
          language,
          officeKind,
          path,
          previewKind,
          source: path,
          url: `file:///${path}`
        }}
      />
    </I18nProvider>
  )

  return rendered
}

describe('LocalFilePreview AI-edit flow', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows the AI-edit toolbar after a gutter line selection', async () => {
    const { container } = renderPreview()

    // Wait for the file text to load into the source view.
    await waitFor(() => {
      expect(readDesktopFileText).toHaveBeenCalled()
    })

    const lineRow = await waitForEl(container, '.select-none.text-right > div')

    await act(async () => {
      fireEvent.click(lineRow)
    })

    expect(slot(container, 'ai-edit-toolbar')).toBeTruthy()
    expect(slot(container, 'ai-edit-open')).toBeTruthy()
  })

  it('injects the selection ref and prompt into the composer on confirm', async () => {
    const refsEvents: unknown[] = []
    const insertEvents: unknown[] = []

    const onRefs = (event: Event) => refsEvents.push((event as CustomEvent).detail)
    const onInsert = (event: Event) => insertEvents.push((event as CustomEvent).detail)

    window.addEventListener(COMPOSER_INSERT_REFS, onRefs)
    window.addEventListener(COMPOSER_INSERT, onInsert)

    const { container } = renderPreview()

    await waitFor(() => {
      expect(readDesktopFileText).toHaveBeenCalled()
    })

    const lineRow = await waitForEl(container, '.select-none.text-right > div')

    await act(async () => {
      fireEvent.click(lineRow)
    })

    await act(async () => {
      fireEvent.click(slot(container, 'ai-edit-open')!)
    })

    // The prompt box mounts in a follow-up render — wait for it before typing.
    await waitFor(() => {
      expect(slot(container, 'ai-edit-prompt-input')).toBeTruthy()
    })

    await act(async () => {
      fireEvent.change(slot(container, 'ai-edit-prompt-input')!, {
        target: { value: 'make it formal' }
      })
    })

    await act(async () => {
      fireEvent.click(slot(container, 'ai-edit-confirm')!)
    })

    window.removeEventListener(COMPOSER_INSERT_REFS, onRefs)
    window.removeEventListener(COMPOSER_INSERT, onInsert)

    // The ref chip: `@line:path:start-end` (single-line pick → no range suffix).
    expect(refsEvents).toHaveLength(1)
    const refsDetail = refsEvents[0] as { refs: unknown[] }

    expect(refsDetail.refs).toHaveLength(1)
    expect(String(refsDetail.refs[0])).toMatch(/^@line:.*notes\.txt:1$/)

    expect(insertEvents).toHaveLength(1)
    const insertDetail = insertEvents[0] as { text: string }

    expect(insertDetail.text).toBe('make it formal')
  })

  it('surfaces a text swipe in the rendered view as an AI selection', async () => {
    const { container } = renderPreview({ language: 'markdown', path: 'C:/repo/notes.md' })

    await waitFor(() => {
      expect(readDesktopFileText).toHaveBeenCalled()
    })

    // A rendered markdown file auto-lands on the rendered view; simulate a
    // text swipe over it and assert the toolbar appears.
    const swipe = {
      isCollapsed: false,
      toString: () => 'second line',
      getRangeAt: () => ({ getBoundingClientRect: () => ({ left: 12, top: 34 }) })
    }

    vi.spyOn(window, 'getSelection').mockReturnValue(swipe as unknown as Selection)

    const scrollContainer = await waitForEl(container, '.min-h-0.flex-1.overflow-auto')

    await act(async () => {
      fireEvent.mouseUp(scrollContainer)
    })

    expect(slot(container, 'ai-edit-toolbar')).toBeTruthy()
  })

  it('mounts the spot editor with AI-edit selection plumbing in edit mode', async () => {
    const { container } = renderPreview()

    await waitFor(() => {
      expect(readDesktopFileText).toHaveBeenCalled()
    })

    // Enter edit mode via the edit button (read-mode header trailing control).
    const editButton = await waitForEl(container, '[data-slot="preview-edit-button"]')

    await act(async () => {
      fireEvent.click(editButton)
    })

    // The CodeMirror host mounts; the AI-edit selection callback is wired to it.
    await waitFor(() => {
      expect(container.querySelector('.cm-content')).toBeTruthy()
    })
  })

  it('renders OfficePreview for office previewKind without the edit button', async () => {
    const { container } = renderPreview({ path: 'C:/report.docx', previewKind: 'office', officeKind: 'docx' })

    // OfficePreview shows its own loading state and eventually renders the
    // OfficePreview chrome.
    await waitFor(() => {
      expect(container.textContent).toContain('Loading Office preview')
    })

    // The text-file edit button should not appear for office files.
    expect(slot(container, 'preview-edit-button')).toBeNull()
  })

  it('hands an Office HTML selection to the composer as @file ref + excerpt', async () => {
    const mammoth = await import('mammoth')
    vi.mocked(mammoth.default.convertToHtml).mockResolvedValue({ messages: [], value: '<p>Edit this paragraph</p>' })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue('data:application/octet-stream;base64,AAAA')

    const refsEvents: unknown[] = []
    const insertEvents: unknown[] = []
    const onRefs = (event: Event) => refsEvents.push((event as CustomEvent).detail)
    const onInsert = (event: Event) => insertEvents.push((event as CustomEvent).detail)

    window.addEventListener(COMPOSER_INSERT_REFS, onRefs)
    window.addEventListener(COMPOSER_INSERT, onInsert)

    const originalGetRect = (Range.prototype as unknown as { getBoundingClientRect?: () => DOMRect }).getBoundingClientRect

    ;(Range.prototype as unknown as { getBoundingClientRect: () => DOMRect }).getBoundingClientRect = () =>
      ({ bottom: 120, height: 20, left: 40, right: 200, top: 100, width: 160, x: 40, y: 100 }) as DOMRect

    const { container } = renderPreview({ path: 'C:/report.docx', previewKind: 'office', officeKind: 'docx' })

    await waitFor(() => {
      expect(container.textContent).toContain('Edit this paragraph')
    })

    const paragraph = container.querySelector('.office-preview p')

    expect(paragraph).not.toBeNull()
    expect(paragraph!.firstChild).not.toBeNull()

    const range = window.document.createRange()
    range.selectNodeContents(paragraph!.firstChild!)

    const selection = window.getSelection()

    if (!selection) {
      throw new Error('window.getSelection() returned null')
    }

    selection.removeAllRanges()
    selection.addRange(range)

    fireEvent.mouseUp(paragraph!)

    await waitFor(() => {
      expect(slot(container, 'ai-edit-toolbar')).toBeTruthy()
    })

    await act(async () => {
      fireEvent.click(slot(container, 'ai-edit-open')!)
    })

    await waitFor(() => {
      expect(slot(container, 'ai-edit-prompt-input')).toBeTruthy()
    })

    await act(async () => {
      fireEvent.change(slot(container, 'ai-edit-prompt-input')!, {
        target: { value: 'make it formal' }
      })
    })

    await act(async () => {
      fireEvent.click(slot(container, 'ai-edit-confirm')!)
    })

    window.removeEventListener(COMPOSER_INSERT_REFS, onRefs)
    window.removeEventListener(COMPOSER_INSERT, onInsert)
    ;(Range.prototype as unknown as { getBoundingClientRect?: () => DOMRect }).getBoundingClientRect = originalGetRect

    expect(refsEvents).toHaveLength(1)

    const refsDetail = refsEvents[0] as { refs: unknown[] }

    expect(refsDetail.refs).toHaveLength(1)
    expect(String(refsDetail.refs[0])).toMatch(/^@file:.*report\.docx$/)

    expect(insertEvents).toHaveLength(1)

    const insertDetail = insertEvents[0] as { text: string }

    expect(insertDetail.text).toContain('Selected text:')
    expect(insertDetail.text).toContain('Edit this paragraph')
    expect(insertDetail.text).toContain('make it formal')
  })
})
