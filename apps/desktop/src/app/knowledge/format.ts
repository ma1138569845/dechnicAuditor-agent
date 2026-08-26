import type { KnowledgeSearchHit } from '@/api/knowledge'

export function formatBytes(bytes: number | undefined): string {
  const num = Number(bytes ?? 0)

  if (!Number.isFinite(num) || num <= 0) {
    return '0 B'
  }

  if (num < 1024) {
    return `${Math.round(num)} B`
  }

  if (num < 1024 * 1024) {
    return `${(num / 1024).toFixed(1).replace(/\.0$/, '')} KB`
  }

  return `${(num / (1024 * 1024)).toFixed(1).replace(/\.0$/, '')} MB`
}

export function formatKbDate(iso: string | undefined): string {
  if (!iso) {
    return ''
  }

  const date = new Date(iso)

  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString()
}

export function formatKbDateTime(iso: string | undefined): string {
  if (!iso) {
    return ''
  }

  const date = new Date(iso)

  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

export function searchHitTitle(hit: KnowledgeSearchHit): string {
  const meta = hit.metadata
  const fromMeta =
    meta && typeof meta.filename === 'string'
      ? meta.filename
      : meta && typeof meta.file_name === 'string'
        ? meta.file_name
        : ''

  return hit.filename || hit.title || fromMeta || ''
}

export function searchHitText(hit: KnowledgeSearchHit): string {
  if (typeof hit.text === 'string' && hit.text.trim()) {
    return hit.text
  }

  if (typeof hit.answer === 'string' && hit.answer.trim()) {
    return hit.answer
  }

  if (typeof hit.content === 'string' && hit.content.trim()) {
    return hit.content
  }

  return ''
}

export function isActiveParseStatus(status: string | undefined): boolean {
  return status === 'pending' || status === 'processing'
}

export function isActiveJobStatus(status: string | undefined): boolean {
  return status === 'pending' || status === 'processing' || status === 'queued' || status === 'running'
}

/** Backend progress is 0–100; the Progress fill expects a 0–1 fraction. */
export function jobProgressFraction(progress: number | undefined): number {
  const num = Number(progress ?? 0)

  if (!Number.isFinite(num) || num <= 0) {
    return 0
  }

  return num > 1 ? Math.min(1, num / 100) : Math.min(1, num)
}

export function ackWasSkipped(result: unknown): boolean {
  return Boolean(result && typeof result === 'object' && 'skipped' in result && (result as { skipped?: boolean }).skipped)
}

export type KnowledgeOfficeKind = 'docx' | 'pptx' | 'xlsx'
export type KnowledgePreviewKind = 'excerpt' | 'image' | 'markdown' | 'office' | 'pdf' | 'text'

const IMAGE_EXT = new Set(['bmp', 'gif', 'jpeg', 'jpg', 'png', 'svg', 'webp'])
const MARKDOWN_EXT = new Set(['markdown', 'md', 'mdown', 'mkd'])
const OFFICE_EXT: Record<string, KnowledgeOfficeKind> = {
  docx: 'docx',
  pptx: 'pptx',
  xlsx: 'xlsx'
}
const TEXT_EXT = new Set(['csv', 'htm', 'html', 'json', 'txt', 'xml'])

export function officeKindForFile(fileName: string | undefined): KnowledgeOfficeKind | null {
  const ext = fileName?.split('.').pop()?.toLowerCase() ?? ''

  return OFFICE_EXT[ext] ?? null
}

export function previewKindForFile(fileName: string | undefined): KnowledgePreviewKind {
  const ext = fileName?.split('.').pop()?.toLowerCase() ?? ''

  if (ext === 'pdf') {
    return 'pdf'
  }

  if (IMAGE_EXT.has(ext)) {
    return 'image'
  }

  if (MARKDOWN_EXT.has(ext)) {
    return 'markdown'
  }

  if (OFFICE_EXT[ext]) {
    return 'office'
  }

  if (TEXT_EXT.has(ext)) {
    return 'text'
  }

  return 'excerpt'
}

/** PDF / Office need a bounded pane so the viewer can fill remaining height. */
export function previewFillsPane(kind: KnowledgePreviewKind): boolean {
  return kind === 'office' || kind === 'pdf'
}

export function decodeBase64Bytes(data: string): Uint8Array {
  const binary = atob(data)
  const bytes = new Uint8Array(binary.length)

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }

  return bytes
}

export function looksLikePdf(bytes: Uint8Array): boolean {
  return bytes.length >= 5 && bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46
}

const WIKI_SECTION = /^(?:[一二三四五六七八九十百]+[、.．]|第[一二三四五六七八九十百\d]+[章节部分篇]|\d+[、.．])\s*\S/

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Turn LLM wiki conventions (numbered lines, bold-only titles) into headings. */
export function wikiArticleMarkdown(content: string, title?: string): string {
  const lines = content.split('\n').map(line => {
    const trimmed = line.trim()

    if (!trimmed || trimmed.startsWith('#')) {
      return line
    }

    const unbolded = trimmed.replace(/^\*\*(.+)\*\*$/, '$1').trim()

    if (WIKI_SECTION.test(unbolded)) {
      return `## ${unbolded}`
    }

    return line
  })

  let markdown = lines.join('\n')

  if (title) {
    markdown = markdown.replace(new RegExp(`^(?:#\\s+)?${escapeRegExp(title)}\\s*\\n+`), '')
  }

  return markdown
}

export function chunkHeading(content: string, index: number): string {
  const line = content.trim().split(/\r?\n/, 1)[0] ?? ''
  const stripped = line.replace(/^#{1,6}\s+/, '').trim()

  return stripped || `#${index + 1}`
}
