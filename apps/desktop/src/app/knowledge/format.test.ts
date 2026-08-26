import { describe, expect, it } from 'vitest'

import type { KnowledgeSearchHit } from '@/api/knowledge'

import {
  ackWasSkipped,
  formatBytes,
  formatKbDate,
  isActiveJobStatus,
  isActiveParseStatus,
  jobProgressFraction,
  searchHitText,
  searchHitTitle
} from './format'

describe('knowledge format helpers', () => {
  it('formats byte sizes without trailing .0 on whole kilobytes', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1024)).toBe('1 KB')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(1024 * 1024)).toBe('1 MB')
  })

  it('returns an empty string for missing dates and a locale date for ISO', () => {
    expect(formatKbDate(undefined)).toBe('')
    expect(formatKbDate('not-a-date')).toBe('not-a-date')
    expect(formatKbDate('2026-01-15T00:00:00Z')).toBe(new Date('2026-01-15T00:00:00Z').toLocaleDateString())
  })

  it('picks a search-hit title from filename, title, or metadata', () => {
    expect(searchHitTitle({ filename: 'a.md' })).toBe('a.md')
    expect(searchHitTitle({ title: 'Intro' })).toBe('Intro')
    expect(searchHitTitle({ metadata: { filename: 'meta.pdf' } })).toBe('meta.pdf')
    expect(searchHitTitle({} as KnowledgeSearchHit)).toBe('')
  })

  it('picks search-hit text from text, answer, or content', () => {
    expect(searchHitText({ text: 'chunk' })).toBe('chunk')
    expect(searchHitText({ answer: 'graph answer' })).toBe('graph answer')
    expect(searchHitText({ content: 'body' })).toBe('body')
    expect(searchHitText({})).toBe('')
  })

  it('treats pending and processing as in-flight parse states', () => {
    expect(isActiveParseStatus('pending')).toBe(true)
    expect(isActiveParseStatus('processing')).toBe(true)
    expect(isActiveParseStatus('completed')).toBe(false)
    expect(isActiveParseStatus('failed')).toBe(false)
  })

  it('treats pending, processing, queued, and running as in-flight jobs', () => {
    expect(isActiveJobStatus('pending')).toBe(true)
    expect(isActiveJobStatus('processing')).toBe(true)
    expect(isActiveJobStatus('queued')).toBe(true)
    expect(isActiveJobStatus('running')).toBe(true)
    expect(isActiveJobStatus('completed')).toBe(false)
    expect(isActiveJobStatus('failed')).toBe(false)
  })

  it('normalizes job progress from percent or fraction into 0–1', () => {
    expect(jobProgressFraction(0)).toBe(0)
    expect(jobProgressFraction(0.4)).toBe(0.4)
    expect(jobProgressFraction(40)).toBe(0.4)
    expect(jobProgressFraction(150)).toBe(1)
  })

  it('detects skipped pipeline acknowledgements', () => {
    expect(ackWasSkipped({ skipped: true })).toBe(true)
    expect(ackWasSkipped({ skipped: false })).toBe(false)
    expect(ackWasSkipped({})).toBe(false)
  })
})
