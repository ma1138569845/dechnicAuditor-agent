/**
 * Office document preview renderer for the right-rail file preview pane.
 *
 * Primary mode: open the file in the local `editor_sdk` (Tencent Docs AI
 * Engine) and render its live WYSIWYG editor in an `<iframe>`. The backend
 * `/api/office-preview/start` endpoint opens the file in editor_sdk and returns
 * an iframe URL of the form
 * ``http://127.0.0.1:<port>/static/<doc|sheet|slide>/pc.html?file_id=xxx``.
 *
 * Fallback mode: when editor_sdk is unavailable, convert the file to readable
 * HTML in the renderer using lightweight npm libraries (mammoth, SheetJS,
 * fflate). This keeps the preview usable offline without requiring any external
 * binary.
 *
 * - .docx: mammoth → sanitized HTML.
 * - .xlsx: SheetJS (xlsx) → sanitized HTML tables, one per worksheet.
 * - .pptx: fflate unzips the OpenXML package and extracts slide text nodes as a
 *   text outline (one section per slide).
 *
 * AI collaboration is agent-driven: the agent edits the open document through
 * the `office_editor` tools (office_open/office_edit/office_save). Text
 * selection for the AI-edit toolbar is only available in the HTML fallback
 * (the editor_sdk iframe is a cross-origin document the renderer cannot read).
 */

import DOMPurify from 'dompurify'
import { strFromU8, unzip } from 'fflate'
import mammoth from 'mammoth'
import type { MouseEvent as ReactMouseEvent } from 'react'
import { memo, useCallback, useEffect, useRef, useState } from 'react'
import * as XLSX from 'xlsx'

import { openExternal } from '@/app/settings/billing/open-external'
import { startOfficePreview, stopOfficePreview } from '@/hermes'
import { useI18n } from '@/i18n'
import type { Translations } from '@/i18n/types'
import { readDesktopFileDataUrl } from '@/lib/desktop-fs'
import { cn } from '@/lib/utils'

export type OfficeKind = 'docx' | 'xlsx' | 'pptx'

type OfficePreviewMode = 'html' | 'iframe'

export interface OfficeAiEditSelection {
  anchorX: number
  anchorY: number
  selectedText: string
  /** True when the report was driven by a mouse-up in the editor. The parent
   *  uses it to dismiss a collapsed pill when the user clicks without changing
   *  the selection (e.g. on the DS ribbon) — the text is unchanged, so it would
   *  otherwise be swallowed by the plugin's dedup. */
  mouseUp?: boolean
}

interface OfficePreviewBaseProps {
  /** When true (the AI-edit prompt box is open), non-interaction empty
   *  selection reports (a no-selection poll) are suppressed so the toolbar and
   *  the typed prompt stay anchored while the user composes. A mouseUp-driven
   *  empty (a real click on empty space / the ribbon) is still forwarded so the
   *  renderer can dismiss the prompt box. When the pill is merely collapsed
   *  this is false and any empty report dismisses it. */
  aiPrompting?: boolean
  officeKind: OfficeKind
  /** Called when the user selects text in the HTML fallback preview. Pass
   *  `null` to clear a previous selection. */
  onAiEditSelection?: (selection: OfficeAiEditSelection | null) => void
  /** Bumped by the parent whenever the file changed on disk (the Electron fs
   *  watch fires after any write — including an agent's office_save). The
   *  preview refreshes from disk: HTML re-renders, the OnlyOffice editor
   *  reloads when clean (banner on conflict), editor_sdk remounts. */
  reloadKey?: number
}

export type OfficePreviewProps = OfficePreviewBaseProps &
  (
    | { arrayBuffer: ArrayBuffer; filePath?: string }
    | { arrayBuffer?: undefined; filePath: string }
  )

type HtmlState =
  | { error: null; html: string; kind: 'ready' }
  | { error: string; kind: 'error' }
  | { kind: 'loading' }

type IframeState =
  | { error: string; errorCode?: string; kind: 'error' }
  | { kind: 'loading' }
  | { kind: 'ready'; engine: string; fileId?: string; previewBaseUrl: string; url: string }

type PreviewMode = 'html' | 'iframe'

function fileIdFromUrl(url: string): string {
  try {
    return new URL(url).searchParams.get('file_id') ?? ''
  } catch {
    return ''
  }
}

function dataUrlToArrayBuffer(dataUrl: string): ArrayBuffer {
  const match = dataUrl.match(/^data:([^,]*),(.*)$/)

  if (!match) {
    throw new Error('Invalid data URL')
  }

  const [, metadata, data] = match
  const isBase64 = metadata.includes(';base64')
  const raw = isBase64 ? atob(data) : decodeURIComponent(data)
  const bytes = new Uint8Array(raw.length)

  for (let i = 0; i < raw.length; i++) {
    bytes[i] = raw.charCodeAt(i)
  }

  return bytes.buffer
}

async function renderDocx(arrayBuffer: ArrayBuffer): Promise<string> {
  // Renderer may not have Node's `Buffer`, while Node tests do. Use whichever
  // input shape mammoth accepts in the current environment.
  const result =
    typeof Buffer !== 'undefined'
      ? await mammoth.convertToHtml({ buffer: Buffer.from(arrayBuffer) })
      : await mammoth.convertToHtml({ arrayBuffer })

  return result.value
}

async function renderXlsx(arrayBuffer: ArrayBuffer): Promise<string> {
  const workbook = XLSX.read(arrayBuffer, { type: 'array' })
  const parts: string[] = []

  for (const sheetName of workbook.SheetNames) {
    const worksheet = workbook.Sheets[sheetName]
    const html = XLSX.utils.sheet_to_html(worksheet, { id: '', editable: false })

    parts.push(`<h3 class="font-semibold text-foreground">${escapeHtml(sheetName)}</h3>`)
    parts.push(html)
  }

  return parts.join('\n')
}

/** Localized labels used by the PPTX HTML fallback outline (renderPptx is a
 *  module-level async function, so it can't call useI18n itself). */
interface PptxLabels {
  slidePage: (slideNumber: number) => string
  noTextContent: string
}

async function renderPptx(arrayBuffer: ArrayBuffer, labels: PptxLabels): Promise<string> {
  const zipped = await new Promise<Record<string, Uint8Array>>((resolve, reject) => {
    unzip(new Uint8Array(arrayBuffer), (err, data) => {
      if (err) {
        reject(err)
      } else {
        resolve(data)
      }
    })
  })

  const slideNames = Object.keys(zipped)
    .filter(name => /^ppt\/slides\/slide\d+\.xml$/.test(name))
    .sort((a, b) => {
      const na = Number.parseInt(a.match(/slide(\d+)\.xml$/)?.[1] ?? '0', 10)
      const nb = Number.parseInt(b.match(/slide(\d+)\.xml$/)?.[1] ?? '0', 10)

      return na - nb
    })

  if (slideNames.length === 0) {
    throw new Error('No readable slides found')
  }

  const parts: string[] = []

  for (const slideName of slideNames) {
    const xml = strFromU8(zipped[slideName])
    // PowerPoint slide text lives in <a:t> elements (a = drawingml main ns).
    const texts: string[] = []
    const textRe = /<a:t>([^<]*)<\/a:t>/g
    let match: RegExpExecArray | null

    while ((match = textRe.exec(xml)) !== null) {
      const text = match[1].trim()

      if (text) {
        texts.push(text)
      }
    }

    const slideNum = Number.parseInt(slideName.match(/slide(\d+)\.xml$/)?.[1] ?? '0', 10)

    parts.push(`<section class="mb-6">`)
    parts.push(`<h3 class="mb-2 text-sm font-semibold text-foreground">${escapeHtml(labels.slidePage(slideNum))}</h3>`)

    if (texts.length === 0) {
      parts.push(`<p class="text-sm text-muted-foreground">${escapeHtml(labels.noTextContent)}</p>`)
    } else {
      parts.push(`<ul class="list-disc space-y-1 pl-5 text-sm text-foreground">`)

      for (const text of texts) {
        parts.push(`<li>${escapeHtml(text)}</li>`)
      }

      parts.push(`</ul>`)
    }

    parts.push(`</section>`)
  }

  return parts.join('\n')
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

const RENDERERS: Record<OfficeKind, (buffer: ArrayBuffer, labels: PptxLabels) => Promise<string>> = {
  docx: renderDocx,
  pptx: renderPptx,
  xlsx: renderXlsx
}

function installMessageForError(office: Translations['preview']['office'], code?: string): string {
  switch (code) {
    case 'OFFICE_SDK_NOT_FOUND':
      return office.installNotFound

    case 'OFFICE_SDK_START_FAILED':
      return office.installStartFailed

    case 'PATH_OUTSIDE_SANDBOX':
      return office.installPathOutsideSandbox

    default:
      return office.installUnavailable
  }
}

export const OfficePreview = memo(function OfficePreview({
  aiPrompting = false,
  arrayBuffer,
  filePath,
  officeKind,
  onAiEditSelection,
  reloadKey = 0
}: OfficePreviewProps) {
  const { t } = useI18n()
  const bytesOnly = Boolean(arrayBuffer) && !filePath
  const [mode, setMode] = useState<PreviewMode>(bytesOnly ? 'html' : 'iframe')
  const [htmlState, setHtmlState] = useState<HtmlState>({ kind: 'loading' })
  const [iframeState, setIframeState] = useState<IframeState>({ kind: 'loading' })
  // Bumping this remounts the <iframe> element (editor_sdk/officecli refresh).
  const [iframeKey, setIframeKey] = useState(0)
  // OnlyOffice banner: the file changed externally while the DS editor holds
  // unsaved edits. Reloading would discard them, so the user chooses.
  const [reloadConflict, setReloadConflict] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)
  // Unsaved-edit flag reported by the OnlyOffice shell (postMessage).
  const dirtyRef = useRef(false)
  const prevReloadKeyRef = useRef(reloadKey)

  // HTML fallback: always render in the background so it is ready if editor_sdk
  // fails or the user explicitly switches to HTML mode.
  useEffect(() => {
    let active = true

    async function load() {
      setHtmlState({ kind: 'loading' })

      try {
        const buffer = arrayBuffer
          ? arrayBuffer
          : dataUrlToArrayBuffer(await readDesktopFileDataUrl(filePath ?? ''))

        if (!active) {
          return
        }

        const html = await RENDERERS[officeKind](buffer, {
          slidePage: slideNumber => t.preview.office.slidePage(slideNumber),
          noTextContent: t.preview.office.noTextContent
        })

        if (!active) {
          return
        }

        setHtmlState({ error: null, html, kind: 'ready' })
      } catch (error) {
        if (!active) {
          return
        }

        setHtmlState({
          error: error instanceof Error ? error.message : String(error),
          kind: 'error'
        })
      }
    }

    void load()

    return () => {
      active = false
    }
    // reloadKey: re-render from the updated bytes after an external (agent)
    // write. The HTML view is read-only, so re-rendering is always safe.
  }, [arrayBuffer, filePath, officeKind, reloadKey, t])

  // editor_sdk iframe: primary preview/edit mode. The backend opens the file
  // in editor_sdk and returns the live WYSIWYG editor's iframe URL.
  // Knowledge-base files arrive as bytes from the backend, so skip the SDK
  // (it needs a renderer-local path) and stay on the HTML conversion.
  useEffect(() => {
    if (!filePath) {
      return
    }

    const path = filePath
    let cancelled = false
    let currentUrl: string | null = null

    async function start() {
      setIframeState({ kind: 'loading' })

      try {
        const result = await startOfficePreview(path)

        if (cancelled) {
          // Do NOT stop by path here. open_office_preview dedupes by path and
          // shares one file_id across concurrent opens, so a superseded start
          // (React StrictMode remounts this effect, or the preview re-opened)
          // stopping by path closes the file_id out from under the active
          // start — its /onlyoffice shell then 404s on the config fetch with
          // "file_id not found". The real unmount cleanup below (currentUrl
          // set) owns the stop; a leftover registry entry is harmless and is
          // reused by the dedup on the next open of the same path.
          return
        }

        if ('error' in result) {
          setIframeState({
            error: installMessageForError(t.preview.office, result.error),
            errorCode: result.error,
            kind: 'error'
          })

          return
        }

        currentUrl = result.url
        setIframeState({
          kind: 'ready',
          url: result.url,
          engine: result.engine,
          fileId: result.file_id,
          previewBaseUrl: result.preview_base_url
        })
      } catch (error) {
        if (cancelled) {
          return
        }

        setIframeState({
          error: error instanceof Error ? error.message : String(error),
          kind: 'error'
        })
      }
    }

    if (mode === 'iframe') {
      void start()
    }

    return () => {
      cancelled = true

      if (currentUrl) {
        void stopOfficePreview(path)
      }
    }
  }, [filePath, mode])

  // When the editor_sdk path fails, quietly fall back to HTML mode so the
  // redundant "切换为 HTML 预览" button disappears and the UI stays clean.
  useEffect(() => {
    if (iframeState.kind === 'error' && mode !== 'html') {
      setMode('html')
    }
  }, [iframeState.kind, mode])

  // Leaving iframe mode (manual "切换为 HTML 预览" switch or the SDK-error
  // fallback above) must clear a stale selection, or the AI-edit toolbar would
  // keep floating over the HTML view with an anchor from the previous engine.
  const prevModeRef = useRef<PreviewMode>(mode)
  useEffect(() => {
    if (prevModeRef.current === 'iframe' && mode === 'html' && onAiEditSelection) {
      onAiEditSelection(null)
    }

    prevModeRef.current = mode
  }, [mode, onAiEditSelection])

  // Bridge text selections from iframe preview engines to the AI-edit toolbar.
  // OnlyOffice posts selections via window.postMessage; editor_sdk xlsx is
  // polled through the preview server's /api/office-selection endpoint because
  // the cross-origin iframe cannot be read directly.
  useEffect(() => {
    if (mode !== 'iframe' || iframeState.kind !== 'ready') {
      return
    }

    const container = wrapperRef.current
    if (!container) {
      return
    }

    const defaultAnchor = () => {
      const rect = container.getBoundingClientRect()

      // Best-effort anchor inside the OnlyOffice editor's document area. The DS
      // reserves roughly the top 15% of the iframe for its ribbon, so pin the
      // pill just below it, horizontally centred — inside the document rather
      // than on the DS chrome. The shell normally measures and sends a precise
      // anchorX/anchorY; this is the fallback for the editor_sdk poll path and
      // for shells that could not measure their iframe.
      return {
        anchorX: rect.left + rect.width / 2,
        anchorY: rect.top + rect.height * 0.15 + 8
      }
    }

    const handleMessage = (event: MessageEvent) => {
      const data = event.data

      if (!data || typeof data !== 'object' || !data.type) {
        return
      }

      // Only trust messages from the preview server that hosts the OnlyOffice
      // shell — the shell posts office-ai-selection / office-editor-state
      // itself, so its origin matches previewBaseUrl (http://127.0.0.1:<port>).
      if (event.origin !== iframeState.previewBaseUrl) {
        return
      }

      if (data.type === 'office-editor-state') {
        dirtyRef.current = Boolean(data.dirty)

        return
      }

      if (data.type !== 'office-ai-selection') {
        return
      }

      if (!onAiEditSelection) {
        return
      }

      if (typeof data.text === 'string' && data.text) {
        // Prefer the anchor reported by the OnlyOffice shell: shell-viewport
        // coordinates of the editor's document-area top-centre (the DS exposes
        // no selection coordinates to plugins in Community Edition, so the shell
        // measures its editor iframe and sends this best-effort position).
        // Translate it into desktop viewport space by adding this iframe's own
        // offset. When the shell couldn't measure it omits anchorX/anchorY and
        // we fall back to the same default below.
        const rect = container.getBoundingClientRect()

        if (typeof data.anchorX === 'number' && typeof data.anchorY === 'number') {
          onAiEditSelection({
            anchorX: rect.left + data.anchorX,
            anchorY: rect.top + data.anchorY,
            mouseUp: data.mouseUp,
            selectedText: data.text
          })
        } else {
          onAiEditSelection({ ...defaultAnchor(), mouseUp: data.mouseUp, selectedText: data.text })
        }
      } else if (!aiPrompting || data.mouseUp) {
        // An empty report dismisses the collapsed pill. While the prompt box is
        // open, only a mouseUp-driven empty (a real click on empty space / the
        // ribbon) dismisses — a no-selection poll is suppressed so the typed
        // prompt isn't thrown away. The editor_sdk poll below keeps its own
        // stricter !aiPrompting gate because it fires every 2s regardless of
        // user interaction.
        onAiEditSelection(null)
      }
    }

    window.addEventListener('message', handleMessage)

    let pollTimer: number | null = null

    if (onAiEditSelection && iframeState.engine === 'editor_sdk' && officeKind === 'xlsx') {
      const pollSelection = async () => {
        try {
          const res = await fetch(
            `${iframeState.previewBaseUrl}/api/office-selection?file_path=${encodeURIComponent(filePath)}`
          )

          if (!res.ok) {
            return
          }

          const data = (await res.json()) as { text?: string | null }

          if (data.text) {
            onAiEditSelection({ ...defaultAnchor(), selectedText: data.text })
          } else if (!aiPrompting) {
            onAiEditSelection(null)
          }
        } catch {
          // Polling is best-effort; ignore transient network errors.
        }
      }

      void pollSelection()
      pollTimer = window.setInterval(pollSelection, 2000)
    }

    return () => {
      window.removeEventListener('message', handleMessage)

      if (pollTimer !== null) {
        window.clearInterval(pollTimer)
      }
    }
  }, [iframeState, mode, officeKind, filePath, onAiEditSelection, aiPrompting])

  // ── External-change refresh ────────────────────────────────────────────
  // The parent bumps reloadKey when the Electron fs watch reports a write to
  // the file. That write can be the OnlyOffice DocumentServer's own save
  // callback (already visible in the editor) or an external one — an agent
  // edit via editor_sdk, a terminal command — that the open editor must
  // reload to show.
  const reloadIframeFromDisk = useCallback(async () => {
    if (iframeState.kind !== 'ready') {
      return
    }

    if (iframeState.engine === 'onlyoffice') {
      // Close + reopen: the backend drops the registry entry, so the next
      // open registers a fresh file_id/key and the DS re-downloads the
      // current on-disk bytes instead of resuming its cached session.
      setReloadConflict(false)
      setIframeState({ kind: 'loading' })

      try {
        await stopOfficePreview(filePath)
        const result = await startOfficePreview(filePath)

        if ('error' in result) {
          setIframeState({
            error: installMessageForError(t.preview.office, result.error),
            errorCode: result.error,
            kind: 'error'
          })

          return
        }

        setIframeState({
          kind: 'ready',
          url: result.url,
          engine: result.engine,
          fileId: result.file_id,
          previewBaseUrl: result.preview_base_url
        })
        dirtyRef.current = false
        setIframeKey(key => key + 1)
      } catch (error) {
        setIframeState({
          error: error instanceof Error ? error.message : String(error),
          kind: 'error'
        })
      }

      return
    }

    // editor_sdk / officecli share one SDK session with the agent's edits, so
    // remounting the SPA re-renders the current session state.
    setIframeKey(key => key + 1)
  }, [filePath, iframeState, t])

  const handleExternalChange = useCallback(async () => {
    if (iframeState.kind !== 'ready' || iframeState.engine !== 'onlyoffice') {
      return
    }

    // Skip writes the DS itself produced (its save callbacks land on disk
    // too) — the editor already shows that content.
    try {
      const fileId = iframeState.fileId ?? fileIdFromUrl(iframeState.url)
      const res = await fetch(
        `${iframeState.previewBaseUrl}/api/onlyoffice/status?file_id=${encodeURIComponent(fileId)}`
      )

      if (!res.ok) {
        return
      }

      const data = (await res.json()) as { changed_externally?: boolean; dirty?: boolean }

      if (data.changed_externally === false) {
        return
      }

      // The shell mirrors its unsaved-edits latch into /status; the message
      // stream is asynchronous and can lag the file-change signal, so trust
      // the latch read straight from the response here, falling back to the
      // live message only if the backend is an older build without it.
      if (dirtyRef.current || data.dirty) {
        setReloadConflict(true)

        return
      }
    } catch {
      return
    }

    void reloadIframeFromDisk()
  }, [iframeState, reloadIframeFromDisk])

  useEffect(() => {
    if (reloadKey === prevReloadKeyRef.current) {
      return
    }

    prevReloadKeyRef.current = reloadKey

    if (mode !== 'iframe' || iframeState.kind !== 'ready') {
      // HTML mode re-renders via its own effect on reloadKey.
      return
    }

    if (iframeState.engine === 'onlyoffice') {
      void handleExternalChange()
    } else {
      setIframeKey(key => key + 1)
    }
  }, [handleExternalChange, iframeState, mode, reloadKey])

  const showHtmlFallback = mode === 'html' || iframeState.kind === 'error'
  const showChrome = Boolean(filePath)

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {showChrome ? (
      <div className="flex h-7 shrink-0 items-center justify-end gap-2 border-b border-border/40 px-3">
        {iframeState.kind !== 'error' && mode === 'html' && (
          <button
            className="text-[0.625rem] font-bold text-muted-foreground underline-offset-4 transition-colors hover:text-foreground"
            onClick={() => setMode('iframe')}
            type="button"
          >
            {t.preview.office.editWithEditorSdk}
          </button>
        )}
        {mode === 'iframe' && htmlState.kind === 'ready' && (
          <button
            className="text-[0.625rem] font-bold text-muted-foreground underline-offset-4 transition-colors hover:text-foreground"
            onClick={() => setMode('html')}
            type="button"
          >
            {t.preview.office.switchToHtml}
          </button>
        )}
        <button
          className="text-[0.625rem] font-bold text-muted-foreground underline-offset-4 transition-colors hover:text-foreground"
          onClick={() => void openExternal(`file:///${filePath}`)}
          type="button"
        >
          {t.preview.office.openWithLocalApp}
        </button>
      </div>
      ) : null}
      <div ref={wrapperRef} className="relative min-h-0 flex-1 overflow-hidden">
        {reloadConflict && (
          <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between gap-2 border-b border-border/60 bg-amber-500/10 px-3 py-1.5">
            <span className="text-[0.6875rem] text-foreground">{t.preview.office.externalChanged}</span>
            <span className="flex shrink-0 items-center gap-2">
              <button
                className="text-[0.625rem] font-bold text-foreground underline-offset-4 transition-colors hover:text-foreground/80"
                onClick={() => void reloadIframeFromDisk()}
                type="button"
              >
                {t.preview.office.reloadDiscard}
              </button>
              <button
                className="text-[0.625rem] font-bold text-muted-foreground underline-offset-4 transition-colors hover:text-foreground"
                onClick={() => setReloadConflict(false)}
                type="button"
              >
                {t.preview.office.keepCurrent}
              </button>
            </span>
          </div>
        )}
        {showHtmlFallback ? (
          <HtmlPreview
            filePath={filePath}
            htmlState={htmlState}
            officeKind={officeKind}
            onAiEditSelection={onAiEditSelection}
          />
        ) : iframeState.kind === 'ready' ? (
          <iframe
            className="h-full w-full border-0 bg-white"
            key={iframeKey}
            src={iframeState.url}
            title={t.preview.office.editWithEditorSdk}
          />
        ) : (
          <div className="grid h-full place-items-center">
            <span className="text-sm text-muted-foreground">{t.preview.office.loading}</span>
          </div>
        )}
      </div>
    </div>
  )
})

interface HtmlPreviewProps {
  filePath?: string
  htmlState: HtmlState
  officeKind: OfficeKind
  onAiEditSelection?: (selection: OfficeAiEditSelection | null) => void
}

function HtmlPreview({ filePath, htmlState, officeKind, onAiEditSelection }: HtmlPreviewProps) {
  const { t } = useI18n()
  const containerRef = useRef<HTMLDivElement>(null)

  const handleMouseUp = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      if (!onAiEditSelection) {
        return
      }

      const target = event.target as HTMLElement

      // Ignore selections initiated on interactive chrome (buttons, links).
      if (target.closest('button') || target.closest('a')) {
        return
      }

      const selection = window.getSelection()

      if (!selection || selection.isCollapsed) {
        onAiEditSelection(null)

        return
      }

      const selectedText = selection.toString().trim()

      if (!selectedText) {
        onAiEditSelection(null)

        return
      }

      const rect = selection.getRangeAt(0).getBoundingClientRect()

      onAiEditSelection({
        anchorX: rect.left,
        anchorY: rect.top,
        selectedText
      })
    },
    [onAiEditSelection]
  )

  const handleMouseDown = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      if (!onAiEditSelection) {
        return
      }

      const target = event.target as HTMLElement

      // Clicking chrome dismisses the toolbar; clicking content lets the mouse-up
      // handler decide whether a new selection was made.
      if (target.closest('button') || target.closest('a')) {
        onAiEditSelection(null)
      }
    },
    [onAiEditSelection]
  )

  if (htmlState.kind === 'loading') {
    return (
      <div className="grid h-full place-items-center">
        <span className="text-sm text-muted-foreground">{t.preview.office.loading}</span>
      </div>
    )
  }

  if (htmlState.kind === 'error') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="text-sm text-muted-foreground">{t.preview.office.cannotPreview(htmlState.error)}</p>
        {filePath ? (
          <button
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
            onClick={() => void openExternal(`file:///${filePath}`)}
            type="button"
          >
            {t.preview.office.openWithSystemApp}
          </button>
        ) : null}
      </div>
    )
  }

  return (
    <div className="h-full overflow-auto px-4 py-4" onMouseDown={handleMouseDown} onMouseUp={handleMouseUp}>
      <div
        className={cn(
          'office-preview prose prose-sm max-w-none dark:prose-invert',
          officeKind === 'xlsx' && 'office-preview-spreadsheet'
        )}
        dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(htmlState.html) }}
        data-selectable-text="true"
        ref={containerRef}
      />
    </div>
  )
}
