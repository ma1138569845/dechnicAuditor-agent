import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { zip } from 'fflate'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { startOfficePreview, stopOfficePreview } from '@/hermes'
import { I18nProvider } from '@/i18n'
import { readDesktopFileDataUrl } from '@/lib/desktop-fs'

import { OfficePreview } from './office-preview'
import type { OfficeAiEditSelection } from './office-preview'

vi.mock('@/hermes', () => ({
  startOfficePreview: vi.fn().mockResolvedValue({
    error: 'unavailable',
    message: 'editor_sdk unavailable'
  }),
  stopOfficePreview: vi.fn()
}))

vi.mock('@/lib/desktop-fs', () => ({
  readDesktopFileDataUrl: vi.fn()
}))

vi.mock('mammoth', () => ({
  default: {
    convertToHtml: vi.fn()
  }
}))

vi.mock('xlsx', () => ({
  utils: {
    sheet_to_html: vi.fn()
  },
  read: vi.fn()
}))

// Minimal valid data URL for an empty 1x1 PNG — the component only needs a
// syntactically valid data URL; actual Office bytes are handled by mocked libs.
const FAKE_DATA_URL = 'data:application/octet-stream;base64,AAAA'

async function makePptxDataUrl(text = 'Slide title'): Promise<string> {
  const encoder = new TextEncoder()

  const slideXml = encoder.encode(`
    <sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <sp><txBody><a:p><a:t>${text}</a:t></a:p></txBody></sp>
    </sld>
  `)

  const zipped = await new Promise<Uint8Array>((resolve, reject) => {
    zip({ 'ppt/slides/slide1.xml': slideXml }, (err, data) => {
      if (err) {
        reject(err)
      } else {
        resolve(data)
      }
    })
  })

  const binary = Array.from(zipped, byte => String.fromCharCode(byte)).join('')

  return `data:application/vnd.openxmlformats-officedocument.presentationml.presentation;base64,${btoa(binary)}`
}

function renderOffice(
  officeKind: 'docx' | 'xlsx' | 'pptx',
  { onAiEditSelection }: { onAiEditSelection?: (selection: OfficeAiEditSelection | null) => void } = {}
) {
  return render(
    <I18nProvider configClient={null}>
      <OfficePreview
        filePath="C:/report.docx"
        officeKind={officeKind}
        onAiEditSelection={onAiEditSelection}
      />
    </I18nProvider>
  )
}

function selectTextNode(container: HTMLElement, text: string) {
  const node = Array.from(container.querySelectorAll('*')).find(el => el.textContent === text)

  if (!node || !node.firstChild) {
    throw new Error(`Text node "${text}" not found`)
  }

  const range = window.document.createRange()
  range.selectNodeContents(node.firstChild)

  const selection = window.getSelection()

  if (!selection) {
    throw new Error('window.getSelection() returned null')
  }

  selection.removeAllRanges()
  selection.addRange(range)

  return range
}

describe('OfficePreview', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders docx HTML from mammoth', async () => {
    const mammoth = await import('mammoth')
    vi.mocked(mammoth.default.convertToHtml).mockResolvedValue({ messages: [], value: '<p>Hello docx</p>' })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const { container } = renderOffice('docx')

    await waitFor(() => {
      expect(container.textContent).toContain('Hello docx')
    })

    expect(container.querySelector('script')).toBeNull()
  })

  it('renders xlsx HTML from SheetJS', async () => {
    const XLSX = await import('xlsx')
    vi.mocked(XLSX.read).mockReturnValue({
      SheetNames: ['Sheet1'],
      Sheets: { Sheet1: {} }
    } as unknown as ReturnType<typeof XLSX.read>)
    vi.mocked(XLSX.utils.sheet_to_html).mockReturnValue('<table><tr><td>42</td></tr></table>')
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const { container } = renderOffice('xlsx')

    await waitFor(() => {
      expect(container.textContent).toContain('42')
    })
  })

  it('renders pptx text outline', async () => {
    // A minimal pptx is a zip containing a single slide XML with \u003ca:t> text.
    // Construct it through the real fflate path so the outline branch is exercised.
    // Build a real zip-backed pptx so the fflate + regex outline branch is exercised.
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(await makePptxDataUrl('Slide title'))

    const { container } = renderOffice('pptx')

    await waitFor(() => {
      expect(container.textContent).toContain('Slide title')
    })
  })

  it('shows an error state and an open button when conversion fails', async () => {
    vi.mocked(readDesktopFileDataUrl).mockRejectedValue(new Error('Disk error'))

    const { container } = renderOffice('docx')

    await waitFor(() => {
      expect(container.textContent).toContain('Cannot preview this Office file')
    })

    expect(container.querySelector('button')).toBeTruthy()
  })

  it('reports selected text on mouseup in HTML fallback', async () => {
    const mammoth = await import('mammoth')
    vi.mocked(mammoth.default.convertToHtml).mockResolvedValue({
      messages: [],
      value: '<p>Edit this paragraph</p>'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const originalGetRect = (Range.prototype as unknown as { getBoundingClientRect?: () => DOMRect }).getBoundingClientRect

    ;(Range.prototype as unknown as { getBoundingClientRect: () => DOMRect }).getBoundingClientRect = () =>
      ({ bottom: 120, height: 20, left: 40, right: 200, top: 100, width: 160, x: 40, y: 100 }) as DOMRect

    const onAiEditSelection = vi.fn()
    const { container } = renderOffice('docx', { onAiEditSelection })

    await waitFor(() => {
      expect(container.textContent).toContain('Edit this paragraph')
    })

    selectTextNode(container, 'Edit this paragraph')

    fireEvent.mouseUp(container.querySelector('.office-preview') ?? container)

    await waitFor(() => {
      expect(onAiEditSelection).toHaveBeenCalledTimes(1)
    })

    const selection = onAiEditSelection.mock.calls[0][0] as OfficeAiEditSelection

    expect(selection.selectedText).toBe('Edit this paragraph')
    expect(selection.anchorX).toBe(40)
    expect(selection.anchorY).toBe(100)

    ;(Range.prototype as unknown as { getBoundingClientRect?: () => DOMRect }).getBoundingClientRect = originalGetRect
  })

  it('clears AI selection when clicking a button in HTML fallback', async () => {
    const mammoth = await import('mammoth')
    vi.mocked(mammoth.default.convertToHtml).mockResolvedValue({
      messages: [],
      value: '<button>Click me</button><p>Edit this paragraph</p>'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const onAiEditSelection = vi.fn()
    const { container } = renderOffice('docx', { onAiEditSelection })

    await waitFor(() => {
      expect(container.textContent).toContain('Click me')
    })

    const contentButton = container.querySelector('.office-preview button')

    expect(contentButton).not.toBeNull()
    fireEvent.mouseDown(contentButton!)

    await waitFor(() => {
      expect(onAiEditSelection).toHaveBeenCalledTimes(1)
    })

    expect(onAiEditSelection).toHaveBeenLastCalledWith(null)
  })

  it('clears AI selection when selection is collapsed', async () => {
    const mammoth = await import('mammoth')
    vi.mocked(mammoth.default.convertToHtml).mockResolvedValue({
      messages: [],
      value: '<p>Edit this paragraph</p>'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const onAiEditSelection = vi.fn()
    const { container } = renderOffice('docx', { onAiEditSelection })

    await waitFor(() => {
      expect(container.textContent).toContain('Edit this paragraph')
    })

    // Ensure no selection is active.
    window.getSelection()?.removeAllRanges()

    fireEvent.mouseUp(container.querySelector('.office-preview') ?? container)

    await waitFor(() => {
      expect(onAiEditSelection).toHaveBeenCalledTimes(1)
    })

    expect(onAiEditSelection).toHaveBeenLastCalledWith(null)
  })

  it('renders the editor_sdk preview URL in an iframe', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({
      url: 'http://127.0.0.1:39099/static/doc/pc.html?file_id=doc_1&local_edit=1',
      engine: 'editor_sdk',
      preview_base_url: 'http://127.0.0.1:39099'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const { container } = renderOffice('docx')

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    const iframe = container.querySelector('iframe') as HTMLIFrameElement

    expect(iframe.getAttribute('src')).toContain('/static/doc/pc.html?file_id=doc_1')
    // The editor_sdk editor is a cross-origin document; no webview preload /
    // selection IPC is attached.
    expect(container.querySelector('webview')).toBeNull()
  })

  it('falls back to HTML preview when editor_sdk reports an error', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({ error: 'OFFICE_SDK_NOT_FOUND', message: 'sdk missing' })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const mammoth = await import('mammoth')
    vi.mocked(mammoth.default.convertToHtml).mockResolvedValue({ messages: [], value: '<p>fallback html</p>' })

    const { container } = renderOffice('docx')

    await waitFor(() => {
      expect(container.textContent).toContain('fallback html')
    })

    expect(container.querySelector('iframe')).toBeNull()
  })

  it('does not report AI selection from the iframe mode', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({
      url: 'http://127.0.0.1:39099/static/doc/pc.html?file_id=doc_1',
      engine: 'editor_sdk',
      preview_base_url: 'http://127.0.0.1:39099'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const onAiEditSelection = vi.fn()
    const { container } = renderOffice('docx', { onAiEditSelection })

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    // A selection made inside the iframe cannot be observed by the renderer —
    // no callback fires from the iframe element itself.
    fireEvent.mouseUp(container.querySelector('iframe') as HTMLElement)

    await waitFor(() => {
      expect(onAiEditSelection).not.toHaveBeenCalled()
    })
  })

  it('reports OnlyOffice selection received via postMessage', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({
      url: 'http://127.0.0.1:39099/onlyoffice?file_id=oo_1',
      engine: 'onlyoffice',
      preview_base_url: 'http://127.0.0.1:39099'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const onAiEditSelection = vi.fn()
    const { container } = renderOffice('docx', { onAiEditSelection })

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    window.postMessage({ type: 'office-ai-selection', text: 'highlighted text' }, '*')

    await waitFor(() => {
      expect(onAiEditSelection).toHaveBeenCalledTimes(1)
    })

    const selection = onAiEditSelection.mock.calls[0][0] as OfficeAiEditSelection

    expect(selection.selectedText).toBe('highlighted text')
    expect(typeof selection.anchorX).toBe('number')
    expect(typeof selection.anchorY).toBe('number')
  })

  it('clears AI selection when postMessage reports no selection', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({
      url: 'http://127.0.0.1:39099/onlyoffice?file_id=oo_1',
      engine: 'onlyoffice',
      preview_base_url: 'http://127.0.0.1:39099'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const onAiEditSelection = vi.fn()
    const { container } = renderOffice('docx', { onAiEditSelection })

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    window.postMessage({ type: 'office-ai-selection', text: null }, '*')

    await waitFor(() => {
      expect(onAiEditSelection).toHaveBeenCalledTimes(1)
    })

    expect(onAiEditSelection).toHaveBeenLastCalledWith(null)
  })

  it('does not stop the preview when a cancelled start resolves after unmount', async () => {
    // The cancelled-start path must not call stopOfficePreview(filePath). The
    // backend dedupes opens by path and shares one file_id across concurrent
    // starts, so a superseded start (React StrictMode remounts this effect in
    // dev) stopping by path closes the file_id out from under the active
    // start's /onlyoffice shell — its config fetch then 404s with "file_id not
    // found".
    let resolveStart: (value: {
      url: string
      engine: string
      preview_base_url: string
    }) => void = () => {}
    vi.mocked(startOfficePreview).mockImplementationOnce(
      () =>
        new Promise<{ url: string; engine: string; preview_base_url: string }>(resolve => {
          resolveStart = resolve
        })
    )
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)
    // afterEach's vi.restoreAllMocks() does not clear the call history of the
    // mocks defined in the vi.mock('@/hermes') factory, so prior iframe tests'
    // unmount cleanups left calls behind — clear them so this test asserts on
    // its own behavior only.
    vi.mocked(stopOfficePreview).mockClear()

    const { unmount } = renderOffice('docx')
    unmount()

    resolveStart({
      url: 'http://127.0.0.1:39099/static/doc/pc.html?file_id=doc_1',
      engine: 'editor_sdk',
      preview_base_url: 'http://127.0.0.1:39099'
    })
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(stopOfficePreview).not.toHaveBeenCalled()
  })
})
