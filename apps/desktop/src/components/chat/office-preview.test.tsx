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
  {
    aiPrompting = false,
    onAiEditSelection,
    reloadKey = 0
  }: {
    aiPrompting?: boolean
    onAiEditSelection?: (selection: OfficeAiEditSelection | null) => void
    reloadKey?: number
  } = {}
) {
  return render(
    <I18nProvider configClient={null}>
      <OfficePreview
        aiPrompting={aiPrompting}
        filePath="C:/report.docx"
        officeKind={officeKind}
        onAiEditSelection={onAiEditSelection}
        reloadKey={reloadKey}
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
    vi.unstubAllGlobals()
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

  it('renders docx HTML from an ArrayBuffer without reading a local path', async () => {
    cleanup()
    vi.mocked(readDesktopFileDataUrl).mockClear()
    vi.mocked(startOfficePreview).mockClear()

    const mammoth = await import('mammoth')
    vi.mocked(mammoth.default.convertToHtml).mockResolvedValue({ messages: [], value: '<p>From bytes</p>' })

    const { container } = render(
      <I18nProvider configClient={null}>
        <OfficePreview arrayBuffer={new Uint8Array([1, 2, 3]).buffer} officeKind="docx" />
      </I18nProvider>
    )

    await waitFor(() => {
      expect(container.textContent).toContain('From bytes')
    })

    expect(readDesktopFileDataUrl).not.toHaveBeenCalled()
    expect(startOfficePreview).not.toHaveBeenCalled()
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
      const last = onAiEditSelection.mock.calls.at(-1)?.[0] as OfficeAiEditSelection | null

      expect(last?.selectedText).toBe('Edit this paragraph')
      expect(last?.anchorX).toBe(40)
      expect(last?.anchorY).toBe(100)
    })

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
      expect(onAiEditSelection).toHaveBeenLastCalledWith(null)
    })
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

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'office-ai-selection', text: 'highlighted text' },
        origin: 'http://127.0.0.1:39099'
      })
    )

    await waitFor(() => {
      expect(onAiEditSelection).toHaveBeenCalledTimes(1)
    })

    const selection = onAiEditSelection.mock.calls[0][0] as OfficeAiEditSelection

    expect(selection.selectedText).toBe('highlighted text')
    expect(typeof selection.anchorX).toBe('number')
    expect(typeof selection.anchorY).toBe('number')
  })

  it('uses the shell-reported anchor when the OnlyOffice message carries one', async () => {
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

    // The shell measures its editor iframe and sends the document-area anchor;
    // the renderer translates it into desktop viewport space by adding this
    // iframe's own offset (zero in jsdom, so the values pass through).
    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'office-ai-selection', text: 'selected', anchorX: 427.4, anchorY: 182.2 },
        origin: 'http://127.0.0.1:39099'
      })
    )

    await waitFor(() => {
      expect(onAiEditSelection).toHaveBeenCalledTimes(1)
    })

    const selection = onAiEditSelection.mock.calls[0][0] as OfficeAiEditSelection

    expect(selection.selectedText).toBe('selected')
    expect(selection.anchorX).toBe(427.4)
    expect(selection.anchorY).toBe(182.2)
  })

  it('forwards the mouseUp flag on a shell selection report', async () => {
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

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'office-ai-selection', text: 'same text', mouseUp: true },
        origin: 'http://127.0.0.1:39099'
      })
    )

    await waitFor(() => {
      expect(onAiEditSelection).toHaveBeenCalledTimes(1)
    })

    const selection = onAiEditSelection.mock.calls[0][0] as OfficeAiEditSelection

    expect(selection.selectedText).toBe('same text')
    expect(selection.mouseUp).toBe(true)
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

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'office-ai-selection', text: null },
        origin: 'http://127.0.0.1:39099'
      })
    )

    await waitFor(() => {
      expect(onAiEditSelection).toHaveBeenCalledTimes(1)
    })

    expect(onAiEditSelection).toHaveBeenLastCalledWith(null)
  })

  it('keeps AI selection alive while the prompt box is open and OnlyOffice reports empty selection', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({
      url: 'http://127.0.0.1:39099/onlyoffice?file_id=oo_1',
      engine: 'onlyoffice',
      preview_base_url: 'http://127.0.0.1:39099'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const onAiEditSelection = vi.fn()
    const { container } = renderOffice('docx', { aiPrompting: true, onAiEditSelection })

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'office-ai-selection', text: null },
        origin: 'http://127.0.0.1:39099'
      })
    )

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(onAiEditSelection).not.toHaveBeenCalled()
  })

  it('forwards an empty selection to dismiss the prompt box when it is mouse-up driven', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({
      url: 'http://127.0.0.1:39099/onlyoffice?file_id=oo_1',
      engine: 'onlyoffice',
      preview_base_url: 'http://127.0.0.1:39099'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const onAiEditSelection = vi.fn()
    const { container } = renderOffice('docx', { aiPrompting: true, onAiEditSelection })

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'office-ai-selection', text: null, mouseUp: true },
        origin: 'http://127.0.0.1:39099'
      })
    )

    await waitFor(() => {
      expect(onAiEditSelection).toHaveBeenCalledTimes(1)
    })

    expect(onAiEditSelection).toHaveBeenLastCalledWith(null)
  })

  it('ignores OnlyOffice selection events from an unexpected origin', async () => {
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

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'office-ai-selection', text: 'highlighted text' },
        origin: 'https://untrusted.example.com'
      })
    )

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(onAiEditSelection).not.toHaveBeenCalled()
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

  it('preserves the DOM selection when the parent re-renders the toolbar', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({ error: 'OFFICE_SDK_NOT_FOUND', message: 'sdk missing' })
    const mammoth = await import('mammoth')
    vi.mocked(mammoth.default.convertToHtml).mockResolvedValue({
      messages: [],
      value: '<p>Keep this highlighted</p>'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)

    const originalGetRect = (Range.prototype as unknown as { getBoundingClientRect?: () => DOMRect }).getBoundingClientRect

    ;(Range.prototype as unknown as { getBoundingClientRect: () => DOMRect }).getBoundingClientRect = () =>
      ({ bottom: 120, height: 20, left: 40, right: 200, top: 100, width: 160, x: 40, y: 100 }) as DOMRect

    const onAiEditSelection = vi.fn()
    const { container, rerender } = renderOffice('docx', { onAiEditSelection })

    await waitFor(() => {
      expect(container.textContent).toContain('Keep this highlighted')
    })

    selectTextNode(container, 'Keep this highlighted')

    fireEvent.mouseUp(container.querySelector('.office-preview') ?? container)

    await waitFor(() => {
      const last = onAiEditSelection.mock.calls.at(-1)?.[0] as OfficeAiEditSelection | null

      expect(last?.selectedText).toBe('Keep this highlighted')
    })

    const selectionBefore = window.getSelection()

    expect(selectionBefore).not.toBeNull()
    expect(selectionBefore!.rangeCount).toBeGreaterThan(0)
    expect(selectionBefore!.toString()).toBe('Keep this highlighted')

    // Re-render the parent with identical props. Without memo this rebuilds the
    // HTML preview DOM and clears the browser selection.
    rerender(
      <I18nProvider configClient={null}>
        <OfficePreview
          filePath="C:/report.docx"
          officeKind="docx"
          onAiEditSelection={onAiEditSelection}
        />
      </I18nProvider>
    )

    const selectionAfter = window.getSelection()

    expect(selectionAfter).not.toBeNull()
    expect(selectionAfter!.rangeCount).toBeGreaterThan(0)
    expect(selectionAfter!.toString()).toBe('Keep this highlighted')

    ;(Range.prototype as unknown as { getBoundingClientRect?: () => DOMRect }).getBoundingClientRect = originalGetRect
  })

  // ── External-change refresh (reloadKey) ───────────────────────────────

  it('re-renders the HTML fallback when reloadKey bumps', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({ error: 'OFFICE_SDK_NOT_FOUND', message: 'sdk missing' })
    const mammoth = await import('mammoth')
    vi.mocked(mammoth.default.convertToHtml).mockResolvedValue({ messages: [], value: '<p>v1</p>' })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)
    // vi.mock factory mocks keep call history across tests; clear before counting.
    vi.mocked(readDesktopFileDataUrl).mockClear()

    const { container, rerender } = renderOffice('docx')

    await waitFor(() => {
      expect(container.textContent).toContain('v1')
    })

    expect(readDesktopFileDataUrl).toHaveBeenCalledTimes(1)

    // An agent save lands on disk -> the parent bumps reloadKey -> the HTML
    // view re-reads the file and re-renders.
    vi.mocked(mammoth.default.convertToHtml).mockResolvedValue({ messages: [], value: '<p>v2</p>' })
    rerender(
      <I18nProvider configClient={null}>
        <OfficePreview filePath="C:/report.docx" officeKind="docx" reloadKey={1} />
      </I18nProvider>
    )

    await waitFor(() => {
      expect(container.textContent).toContain('v2')
    })

    expect(readDesktopFileDataUrl).toHaveBeenCalledTimes(2)
  })

  it('auto-reloads the OnlyOffice editor after an external change when clean', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({
      url: 'http://127.0.0.1:39099/onlyoffice?file_id=oo_1',
      engine: 'onlyoffice',
      file_id: 'oo_1',
      preview_base_url: 'http://127.0.0.1:39099'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'saved', changed_externally: true })
      })
    )

    const { container, rerender } = renderOffice('docx', { onAiEditSelection: vi.fn() })

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    // The shell reports the editor has no unsaved edits.
    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'office-editor-state', dirty: false },
        origin: 'http://127.0.0.1:39099'
      })
    )

    vi.mocked(stopOfficePreview).mockClear()
    vi.mocked(startOfficePreview).mockClear()

    rerender(
      <I18nProvider configClient={null}>
        <OfficePreview
          filePath="C:/report.docx"
          officeKind="docx"
          onAiEditSelection={vi.fn()}
          reloadKey={1}
        />
      </I18nProvider>
    )

    // Close + reopen: the backend drops the registry entry so the DS
    // re-downloads the (AI-edited) on-disk bytes.
    await waitFor(() => {
      expect(stopOfficePreview).toHaveBeenCalledWith('C:/report.docx')
    })

    await waitFor(() => {
      expect(startOfficePreview).toHaveBeenCalledTimes(1)
    })
  })

  it('asks before reloading the OnlyOffice editor when it holds unsaved edits', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({
      url: 'http://127.0.0.1:39099/onlyoffice?file_id=oo_1',
      engine: 'onlyoffice',
      file_id: 'oo_1',
      preview_base_url: 'http://127.0.0.1:39099'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'saved', changed_externally: true })
      })
    )

    const { container, rerender } = renderOffice('docx', { onAiEditSelection: vi.fn() })

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    // The user has typed — the DS editor is dirty, reloading would discard it.
    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'office-editor-state', dirty: true },
        origin: 'http://127.0.0.1:39099'
      })
    )

    vi.mocked(stopOfficePreview).mockClear()
    vi.mocked(startOfficePreview).mockClear()

    rerender(
      <I18nProvider configClient={null}>
        <OfficePreview
          filePath="C:/report.docx"
          officeKind="docx"
          onAiEditSelection={vi.fn()}
          reloadKey={1}
        />
      </I18nProvider>
    )

    await waitFor(() => {
      expect(container.textContent).toContain('Reload & discard')
    })

    expect(stopOfficePreview).not.toHaveBeenCalled()
    expect(startOfficePreview).not.toHaveBeenCalled()

    // The user consents to discarding their unsaved edits.
    const reloadButton = Array.from(container.querySelectorAll('button')).find(
      button => button.textContent === 'Reload & discard'
    )

    expect(reloadButton).toBeTruthy()
    fireEvent.click(reloadButton as HTMLElement)

    await waitFor(() => {
      expect(stopOfficePreview).toHaveBeenCalledWith('C:/report.docx')
    })

    await waitFor(() => {
      expect(startOfficePreview).toHaveBeenCalledTimes(1)
    })
  })

  it('asks before reloading when the status latch reports unsaved edits', async () => {
    // The shell mirrors its edited-since-save latch into /status, so the
    // refresh decision reads it from the status response — the async
    // postMessage stream may lag the file-change signal.
    vi.mocked(startOfficePreview).mockResolvedValue({
      url: 'http://127.0.0.1:39099/onlyoffice?file_id=oo_1',
      engine: 'onlyoffice',
      file_id: 'oo_1',
      preview_base_url: 'http://127.0.0.1:39099'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'saved', changed_externally: true, dirty: true })
      })
    )

    const { container, rerender } = renderOffice('docx', { onAiEditSelection: vi.fn() })

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    // NOTE: no office-editor-state message is dispatched — the latch arrives
    // via the status fetch alone.
    vi.mocked(stopOfficePreview).mockClear()
    vi.mocked(startOfficePreview).mockClear()

    rerender(
      <I18nProvider configClient={null}>
        <OfficePreview
          filePath="C:/report.docx"
          officeKind="docx"
          onAiEditSelection={vi.fn()}
          reloadKey={1}
        />
      </I18nProvider>
    )

    await waitFor(() => {
      expect(container.textContent).toContain('Reload & discard')
    })

    expect(stopOfficePreview).not.toHaveBeenCalled()
    expect(startOfficePreview).not.toHaveBeenCalled()
  })

  it('ignores a write the DocumentServer itself produced', async () => {
    vi.mocked(startOfficePreview).mockResolvedValue({
      url: 'http://127.0.0.1:39099/onlyoffice?file_id=oo_1',
      engine: 'onlyoffice',
      file_id: 'oo_1',
      preview_base_url: 'http://127.0.0.1:39099'
    })
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(FAKE_DATA_URL)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'saved', changed_externally: false })
      })
    )

    const { container, rerender } = renderOffice('docx', { onAiEditSelection: vi.fn() })

    await waitFor(() => {
      expect(container.querySelector('iframe')).toBeTruthy()
    })

    vi.mocked(stopOfficePreview).mockClear()
    vi.mocked(startOfficePreview).mockClear()

    rerender(
      <I18nProvider configClient={null}>
        <OfficePreview
          filePath="C:/report.docx"
          officeKind="docx"
          onAiEditSelection={vi.fn()}
          reloadKey={1}
        />
      </I18nProvider>
    )

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(stopOfficePreview).not.toHaveBeenCalled()
    expect(startOfficePreview).not.toHaveBeenCalled()
  })
})
