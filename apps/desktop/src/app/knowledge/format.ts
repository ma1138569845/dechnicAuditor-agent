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
