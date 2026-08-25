// Pure derivation for the assistant message's artifact cards: fold a turn's
// file-edit tool parts into one row per file. No React/DOM.

import {
  countDiffLineStats,
  fileEditBasename,
  fileEditPath,
  inlineDiffFromResult,
  isFileEditTool,
  numberValue,
  parseMaybeObject
} from '@/components/assistant-ui/tool/fallback-model'
import { mediaKind, mediaPathFromMarkdownHref } from '@/lib/media'
import { firstStringField } from '@/lib/text'

export interface ChangedFile {
  added: number
  /** UTF-8 byte size when the tool reported it (write_file) or the write
   *  payload is still on the call. Patches often have none. */
  byteSize?: number
  /** Basename, for the card label. */
  name: string
  /** Path exactly as the tool reported it (absolute or repo-relative). */
  path: string
  removed: number
}

interface ChangedFilePart {
  args?: unknown
  isError?: boolean
  result?: unknown
  text?: unknown
  toolName?: unknown
  type?: unknown
}

const HTML_PATH_RE = /\.html?$/i
const MARKDOWN_LINK_RE = /\[[^\]]*\]\(([^)\s]+)\)/g
const utf8 = new TextEncoder()

/** Office documents land via the office_editor toolset, not write_file
 *  (they're ZIP packages, not patchable text). Same deliverable as a markdown
 *  write: a file the user should be able to open from the transcript cards. */
const OFFICE_ARTIFACT_TOOL_NAMES = new Set(['office_create', 'office_save'])

export function isHtmlPath(path: string): boolean {
  return HTML_PATH_RE.test(path.replace(/[?#].*$/, ''))
}

/** Compact size label in the Cursor/Finder shape (`4.8 KB`), or empty when
 *  the tool never told us how big the file is. */
export function formatChangedFileSize(bytes: number | undefined): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) {
    return ''
  }

  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0

  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }

  const rounded = value >= 10 || unit === 0 ? value.toFixed(0) : value.toFixed(1)

  return `${rounded} ${units[unit]}`
}

function fileEditFailed(part: ChangedFilePart, result: Record<string, unknown>): boolean {
  return (
    part.isError === true ||
    result.success === false ||
    result.ok === false ||
    Boolean(firstStringField(result, ['error']))
  )
}

function isArtifactProducerTool(toolName: string): boolean {
  return isFileEditTool(toolName) || OFFICE_ARTIFACT_TOOL_NAMES.has(toolName)
}

/** `file_id` from editor_sdk is an opaque token (`new_doc_xxx`); only keep
 *  values that look like a real filesystem path. */
function isLikelyFsPath(value: string): boolean {
  return /[\\/]/.test(value) || /^[A-Za-z]:/.test(value) || /\.[a-z0-9]{1,8}$/i.test(value)
}

function artifactFilePath(args: Record<string, unknown>, result: Record<string, unknown>): string {
  const candidates = [
    fileEditPath(args, result),
    firstStringField(args, ['file_path', 'save_path']),
    firstStringField(result, ['file_path', 'save_path'])
  ]

  for (const candidate of candidates) {
    if (candidate && isLikelyFsPath(candidate)) {
      return candidate
    }
  }

  return ''
}

function rememberArtifact(
  byPath: Map<string, ChangedFile>,
  path: string,
  stats?: { added: number; removed: number },
  byteSize?: number
) {
  const existing = byPath.get(path)

  if (existing) {
    if (stats) {
      existing.added += stats.added
      existing.removed += stats.removed
    }

    if (byteSize != null) {
      existing.byteSize = byteSize
    }

    return
  }

  byPath.set(path, {
    added: stats?.added ?? 0,
    byteSize,
    name: fileEditBasename(path),
    path,
    removed: stats?.removed ?? 0
  })
}

function artifactPathFromMarkdownHref(href: string): string | null {
  const path = mediaPathFromMarkdownHref(href)

  if (!path || mediaKind(path) !== 'file') {
    return null
  }

  return path
}

function collectTextArtifactFiles(text: string, byPath: Map<string, ChangedFile>) {
  for (const match of text.matchAll(MARKDOWN_LINK_RE)) {
    const path = artifactPathFromMarkdownHref(match[1] ?? '')

    if (path) {
      rememberArtifact(byPath, path)
    }
  }
}

function fileEditByteSize(args: Record<string, unknown>, result: Record<string, unknown>): number | undefined {
  const written = numberValue(result.bytes_written)

  if (written != null && written >= 0) {
    return written
  }

  const content = firstStringField(args, ['content', 'contents', 'text'])

  if (!content) {
    return undefined
  }

  return utf8.encode(content).length
}

/**
 * One card per file the turn wrote, in first-touched order, with the +/- of
 * every edit to that file summed. Landed writes count even without a persisted
 * diff (`write_file` creates rehydrate that way). Office files the agent built
 * via python-docx / terminal show up as MEDIA links in the text — those count
 * too. A call still running has no result, and a failed one changed nothing.
 */
export function deriveChangedFiles(parts: readonly unknown[]): ChangedFile[] {
  const byPath = new Map<string, ChangedFile>()

  for (const raw of parts) {
    const part = (raw ?? {}) as ChangedFilePart

    if (part.type === 'text' && typeof part.text === 'string') {
      collectTextArtifactFiles(part.text, byPath)
      continue
    }

    if (part.type !== 'tool-call' || typeof part.toolName !== 'string' || !isArtifactProducerTool(part.toolName)) {
      continue
    }

    if (part.result === undefined) {
      continue
    }

    const args = parseMaybeObject(part.args)
    const result = parseMaybeObject(part.result)

    if (fileEditFailed(part, result)) {
      continue
    }

    const path = artifactFilePath(args, result)

    if (!path) {
      continue
    }

    const diff = inlineDiffFromResult(result)
    const stats = diff ? countDiffLineStats(diff) : { added: 0, removed: 0 }

    rememberArtifact(byPath, path, stats, fileEditByteSize(args, result))
  }

  return [...byPath.values()]
}
