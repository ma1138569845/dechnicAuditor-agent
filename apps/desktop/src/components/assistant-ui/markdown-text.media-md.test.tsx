import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { isMarkdownDocumentPath, mediaMarkdownHref } from '@/lib/media'

import { MarkdownTextContent } from './markdown-text'

// Regression for #84951 and Office MEDIA: a file delivered via MEDIA has no
// entry in MEDIA_BY_EXT, so it classified as a generic 'file' and rendered as
// a download-style `Open …` link (and Windows paths percent-encoded the
// basename). Documents — markdown, Office, PDF, zip — must route to the
// preview rail instead.
describe('markdown documents delivered via MEDIA', () => {
  afterEach(cleanup)

  it('classifies markdown extensions as markdown documents', () => {
    expect(isMarkdownDocumentPath('/tmp/report.md')).toBe(true)
    expect(isMarkdownDocumentPath('/tmp/notes.markdown')).toBe(true)
    expect(isMarkdownDocumentPath('C:\\Users\\a\\report.MD')).toBe(true)
    expect(isMarkdownDocumentPath('/tmp/report.md?x=1')).toBe(true)
    expect(isMarkdownDocumentPath('/tmp/archive.zip')).toBe(false)
    expect(isMarkdownDocumentPath('/tmp/clip.mp4')).toBe(false)
    expect(isMarkdownDocumentPath('/tmp/README')).toBe(false)
  })

  it('renders a MEDIA .md as a preview attachment, not a download link', async () => {
    const href = mediaMarkdownHref('/home/user/out/report.md')

    render(<MarkdownTextContent isRunning={false} text={`[report.md](${href})`} />)

    // PreviewAttachment renders an "open preview" toggle button; the old
    // MediaAttachment 'file' fallback rendered a bare "Open ..." anchor.
    // Two buttons now: Download + Open preview (maintainer-requested).
    const buttons = await screen.findAllByRole('button')
    expect(buttons.length).toBe(2)
    expect(screen.getByText('Download')).toBeTruthy()
    expect(screen.queryByText(/^Loading /)).toBeNull()
    expect(screen.getByText('report.md')).toBeTruthy()
  })

  it('renders a MEDIA office document as a preview attachment, not an Open download link', async () => {
    const path = 'C:/Users/Dechnic/projects/energy-audit/能源审计技能体系介绍.docx'
    const href = mediaMarkdownHref(path)

    render(<MarkdownTextContent isRunning={false} text={`[File: 能源审计技能体系介绍.docx](${href})`} />)

    expect(await screen.findByRole('button', { name: 'Open preview' })).toBeTruthy()
    expect(screen.getByText('能源审计技能体系介绍.docx')).toBeTruthy()
    expect(screen.queryByText(/^Loading /)).toBeNull()
    expect(screen.queryByText(/%E8%83%BD/)).toBeNull()
  })

  it('renders a non-markdown MEDIA file as a preview attachment too', async () => {
    // Extends #84951 to every non-media extension: PDFs, archives, data
    // files. MediaAttachment's kind==='file' branch was a degraded dead-end
    // (bare "Open ..." anchor, verified live with .pdf and .qzx7 — the
    // markdown-LINK path already gave these a proper file card). MEDIA:
    // must never render worse than a plain markdown link to the same file.
    const href = mediaMarkdownHref('/home/user/out/archive.zip')

    render(<MarkdownTextContent isRunning={false} text={`[archive.zip](${href})`} />)

    const buttons = await screen.findAllByRole('button')
    expect(buttons.length).toBe(2)
    expect(screen.getByText('Download')).toBeTruthy()
    expect(screen.getByText('archive.zip')).toBeTruthy()
    expect(screen.queryByText(/^Open archive/)).toBeNull()
  })

  it('renders a MEDIA pdf as a preview attachment', async () => {
    const href = mediaMarkdownHref('C:/Users/a/report.pdf')

    render(<MarkdownTextContent isRunning={false} text={`[report.pdf](${href})`} />)

    const buttons = await screen.findAllByRole('button')
    expect(buttons.length).toBe(2)
    expect(screen.getByText('report.pdf')).toBeTruthy()
  })
})
