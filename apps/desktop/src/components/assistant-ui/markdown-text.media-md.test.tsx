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
    expect(await screen.findByRole('button')).toBeTruthy()
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

  it('renders MEDIA zip/pdf through the preview rail instead of the download fallback', async () => {
    const href = mediaMarkdownHref('/home/user/out/archive.zip')

    render(<MarkdownTextContent isRunning={false} text={`[archive.zip](${href})`} />)

    expect(await screen.findByRole('button', { name: 'Open preview' })).toBeTruthy()
    expect(screen.getByText('archive.zip')).toBeTruthy()
    expect(screen.queryByText(/^Open archive\.zip$/)).toBeNull()
  })
})
