import { describe, expect, it } from 'vitest'

import { mediaDisplayLabel, mediaKind, mediaName, mediaPathFromMarkdownHref } from './media'

describe('mediaName', () => {
  it('takes the basename of a posix path', () => {
    expect(mediaName('/home/user/out/report.md')).toBe('report.md')
  })

  it('does not treat a Windows drive path as a URL', () => {
    // WHATWG `new URL('C:/Users/…/中文.docx')` succeeds with protocol `c:` and
    // percent-encodes the pathname — that used to paint `Open %E8%83%BD…`.
    const path = 'C:/Users/Dechnic/projects/energy-audit/能源审计技能体系介绍.docx'

    expect(mediaName(path)).toBe('能源审计技能体系介绍.docx')
    expect(mediaName(path.replace(/\//g, '\\'))).toBe('能源审计技能体系介绍.docx')
  })

  it('decodes a percent-encoded basename without using URL()', () => {
    expect(mediaName('C:/out/%E8%83%BD%E6%BA%90%E5%AE%A1%E8%AE%A1.docx')).toBe('能源审计.docx')
  })

  it('still uses the URL pathname for http(s) media', () => {
    expect(mediaName('https://cdn.example/files/clip.mp4?token=1')).toBe('clip.mp4')
  })
})

describe('mediaPathFromMarkdownHref', () => {
  it('strips markdown bold leaked into a stored media href', () => {
    expect(mediaPathFromMarkdownHref('#media:C%3A%2Fout%2F%E6%8A%A5%E5%91%8A.docx%2A%2A')).toBe('C:/out/报告.docx')
  })
})

describe('mediaDisplayLabel', () => {
  it('labels an office document as a file with a readable name', () => {
    expect(mediaKind('C:/out/报告.docx')).toBe('file')
    expect(mediaDisplayLabel('C:/out/报告.docx')).toBe('File: 报告.docx')
  })
})
