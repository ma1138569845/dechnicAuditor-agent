import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { startOfficePreview } from '@/hermes'
import { I18nProvider } from '@/i18n'
import { readDesktopFileDataUrl, readDesktopFileText } from '@/lib/desktop-fs'

import { LocalFilePreview, MarkdownPreview } from './preview-file'

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

// Keep the real hermes module (I18nProvider and the preview component tree use
// many of its exports) and only stub the OnlyOffice preview lifecycle so the
// office tests below can drive a ready iframe instead of a real backend.
//
// The default must THROW synchronously — exactly like the real call does in
// jsdom (window.hermesDesktop is undefined), where the preview server bridge
// rejects before the await. A microtask-rejected promise lands the error a
// tick later and flips the HTML-fallback mouse-up timing, breaking the
// existing HTML-selection tests. Tests that need a live editor override this
// with a resolved URL.
vi.mock('@/hermes', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hermes')>()
  return {
    ...actual,
    startOfficePreview: vi.fn(() => {
      throw new Error('unavailable')
    }),
    stopOfficePreview: vi.fn()
  }
})

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

  const OFFICE_ORIGIN = 'http://127.0.0.1:39099'

  function mountOfficeIframe() {
    vi.mocked(startOfficePreview).mockResolvedValue({
      url: `${OFFICE_ORIGIN}/onlyoffice?file_id=oo_1`,
      engine: 'onlyoffice',
      preview_base_url: OFFICE_ORIGIN
    })
    return renderPreview({ path: 'C:/report.docx', previewKind: 'office', officeKind: 'docx' })
  }

  function sendOfficeSelection(text: string | null, mouseUp = false) {
    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'office-ai-selection', text, mouseUp },
        origin: OFFICE_ORIGIN
      })
    )
  }

  it('dismisses the collapsed AI pill when OnlyOffice reports an empty selection', async () => {
    const { container } = mountOfficeIframe()

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    sendOfficeSelection('report text')
    await waitFor(() => {
      expect(slot(container, 'ai-edit-toolbar')).toBeTruthy()
    })

    // Clicking empty space clears the selection; the report must dismiss the pill.
    sendOfficeSelection(null)

    await waitFor(() => {
      expect(slot(container, 'ai-edit-toolbar')).toBeNull()
    })
  })

  it('keeps the prompt box when an empty selection is reported while composing', async () => {
    const { container } = mountOfficeIframe()

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    sendOfficeSelection('report text')
    await waitFor(() => {
      expect(slot(container, 'ai-edit-toolbar')).toBeTruthy()
    })

    await act(async () => {
      fireEvent.click(slot(container, 'ai-edit-open')!)
    })
    await waitFor(() => {
      expect(slot(container, 'ai-edit-prompt-input')).toBeTruthy()
    })

    // While composing, a cleared selection must not throw away the prompt.
    sendOfficeSelection(null)
    await new Promise(resolve => setTimeout(resolve, 50))

    expect(slot(container, 'ai-edit-toolbar')).toBeTruthy()
    expect(slot(container, 'ai-edit-prompt-input')).toBeTruthy()
  })

  it('dismisses the prompt box when an empty mouse-up report arrives while composing', async () => {
    const { container } = mountOfficeIframe()

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    sendOfficeSelection('report text')
    await waitFor(() => {
      expect(slot(container, 'ai-edit-toolbar')).toBeTruthy()
    })

    await act(async () => {
      fireEvent.click(slot(container, 'ai-edit-open')!)
    })
    await waitFor(() => {
      expect(slot(container, 'ai-edit-prompt-input')).toBeTruthy()
    })

    // A mouseUp-driven empty (a real click on empty space / the ribbon in the
    // editor) dismisses the dialog even while composing — unlike a
    // non-interaction poll empty, which the previous test keeps.
    sendOfficeSelection(null, true)

    await waitFor(() => {
      expect(slot(container, 'ai-edit-toolbar')).toBeNull()
    })
  })

  it('dismisses the AI pill when the user clicks the unchanged selection (DS ribbon)', async () => {
    const { container } = mountOfficeIframe()

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    sendOfficeSelection('same text')
    await waitFor(() => {
      expect(slot(container, 'ai-edit-toolbar')).toBeTruthy()
    })

    // The plugin force-reports the unchanged selection on mouse-up; the parent
    // must recognise it as "clicked without changing" and dismiss.
    sendOfficeSelection('same text', true)

    await waitFor(() => {
      expect(slot(container, 'ai-edit-toolbar')).toBeNull()
    })
  })

  it('dismisses the prompt box when the unchanged selection is clicked while composing', async () => {
    const { container } = mountOfficeIframe()

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    sendOfficeSelection('same text')
    await waitFor(() => {
      expect(slot(container, 'ai-edit-toolbar')).toBeTruthy()
    })

    await act(async () => {
      fireEvent.click(slot(container, 'ai-edit-open')!)
    })
    await waitFor(() => {
      expect(slot(container, 'ai-edit-prompt-input')).toBeTruthy()
    })

    // Clicking the unchanged selection in the editor is a real mouse-up: while
    // the prompt box is open it means the user clicked elsewhere, so the dialog
    // must dismiss. (A non-interaction empty report while composing is still
    // kept — see the previous test.)
    sendOfficeSelection('same text', true)

    await waitFor(() => {
      expect(slot(container, 'ai-edit-toolbar')).toBeNull()
    })
  })
})
// Behavior tests for the .md file preview renderer: input markdown goes
// through normalizeFilePreviewMath -> Streamdown (+ KaTeX math plugin) and must
// come out as real rendered elements, matching what the chat transcript
// renderer produces. Guards the regression where the preview was a bare
// Streamdown pass with no math plugin and no table/img/a components.
describe('MarkdownPreview', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders block and inline math through KaTeX', () => {
    // KaTeX marks its output; raw "$" delimiters must be gone.
    const { container } = render(
      <MarkdownPreview
        text={'Formula:\n\n$$\nx = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}\n$$\n\nInline $a^2 + b^2 = c^2$ too.'}
      />
    )

    expect(container.querySelector('.katex')).not.toBeNull()
    expect(screen.queryByText(/\$\$/)).toBeNull()
  })

  it('renders GFM tables with header and body cells', () => {
    const { container } = render(<MarkdownPreview text={'| h1 | h2 |\n| --- | --- |\n| a | b |'} />)

    const table = container.querySelector('table')
    expect(table).not.toBeNull()
    expect(table?.querySelector('thead th')?.textContent).toBe('h1')
    expect(table?.querySelector('tbody td')?.textContent).toBe('a')
  })

  it('renders images with alt text', () => {
    const { container } = render(<MarkdownPreview text={'![a chart](https://example.com/chart.png)'} />)

    const img = container.querySelector('img')
    expect(img?.getAttribute('alt')).toBe('a chart')
    expect(img?.getAttribute('src')).toBe('https://example.com/chart.png')
  })

  it('renders external links to open in a new tab safely', () => {
    const { container } = render(<MarkdownPreview text={'[docs](https://example.com/docs)'} />)

    const anchor = container.querySelector('a')
    expect(anchor?.getAttribute('href')).toBe('https://example.com/docs')
    expect(anchor?.getAttribute('target')).toBe('_blank')
    expect(anchor?.getAttribute('rel')).toBe('noopener noreferrer')
  })
})
