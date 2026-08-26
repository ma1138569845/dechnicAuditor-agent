import { describe, expect, it } from 'vitest'

import type { KnowledgeSearchHit } from '@/api/knowledge'

import {
  ackWasSkipped,
  chunkHeading,
  formatBytes,
  formatKbDate,
  isActiveJobStatus,
  isActiveParseStatus,
  jobProgressFraction,
  decodeBase64Bytes,
  looksLikePdf,
  officeKindForFile,
  previewFillsPane,
  previewKindForFile,
  searchHitText,
  searchHitTitle,
  wikiArticleMarkdown
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

describe('knowledge preview helpers', () => {
  it('classifies preview kind from the file name', () => {
    expect(previewKindForFile('report.pdf')).toBe('pdf')
    expect(previewKindForFile('photo.PNG')).toBe('image')
    expect(previewKindForFile('notes.md')).toBe('markdown')
    expect(previewKindForFile('plain.txt')).toBe('text')
    expect(previewKindForFile('slides.pptx')).toBe('office')
    expect(previewKindForFile('memo.docx')).toBe('office')
    expect(previewKindForFile('sheet.xlsx')).toBe('office')
    expect(previewKindForFile('legacy.doc')).toBe('excerpt')
  })

  it('maps office files to a renderer kind and fills the pane for pdf/office', () => {
    expect(officeKindForFile('memo.DOCX')).toBe('docx')
    expect(officeKindForFile('sheet.xlsx')).toBe('xlsx')
    expect(officeKindForFile('slides.pptx')).toBe('pptx')
    expect(officeKindForFile('notes.md')).toBeNull()
    expect(previewFillsPane('pdf')).toBe(true)
    expect(previewFillsPane('office')).toBe(true)
    expect(previewFillsPane('markdown')).toBe(false)
  })

  it('decodes base64 payloads and recognizes a PDF header', () => {
    const pdf = decodeBase64Bytes(btoa('%PDF-1.4 mock'))

    expect(looksLikePdf(pdf)).toBe(true)
    expect(new TextDecoder().decode(pdf).startsWith('%PDF-1.4')).toBe(true)
    expect(looksLikePdf(new Uint8Array([0x50, 0x4b, 0x03, 0x04]))).toBe(false)
  })

  it('uses the first markdown heading as the chunk title', () => {
    expect(chunkHeading('# 第1章 执行摘要\nbody', 0)).toBe('第1章 执行摘要')
    expect(chunkHeading('no heading here', 3)).toBe('no heading here')
    expect(chunkHeading('', 3)).toBe('#4')
  })

  it('promotes wiki section lines into markdown headings', () => {
    const markdown = wikiArticleMarkdown(
      ['岚山区巨峰中心卫生院能源审计报告', '', '一、 审计范围与方法', '正文一段。', '', '**二、建筑概况**', '医院占地。'].join('\n'),
      '岚山区巨峰中心卫生院能源审计报告'
    )

    expect(markdown).toContain('## 一、 审计范围与方法')
    expect(markdown).toContain('## 二、建筑概况')
    expect(markdown).toContain('正文一段。')
    expect(markdown.includes('岚山区巨峰中心卫生院能源审计报告')).toBe(false)
    expect(markdown.startsWith('# ')).toBe(false)
  })
})
