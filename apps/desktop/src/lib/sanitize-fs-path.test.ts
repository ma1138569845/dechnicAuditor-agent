import { describe, expect, it } from 'vitest'

import { sanitizeFsPath } from './sanitize-fs-path'

describe('sanitizeFsPath', () => {
  it('strips bold wrappers leaked onto a deliverable path', () => {
    expect(sanitizeFsPath('~/out/烟台经济技术开发区人民法院能源审计报告.docx**')).toBe(
      '~/out/烟台经济技术开发区人民法院能源审计报告.docx'
    )
    expect(sanitizeFsPath('**~/out/报告.pdf**')).toBe('~/out/报告.pdf')
    expect(sanitizeFsPath('C:/out/报告.docx**')).toBe('C:/out/报告.docx')
  })

  it('peels paired quotes and leftover unpaired backticks', () => {
    expect(sanitizeFsPath('`~/out/a.docx`')).toBe('~/out/a.docx')
    expect(sanitizeFsPath('"C:/out/a.pdf"')).toBe('C:/out/a.pdf')
    expect(sanitizeFsPath('`~/out/a.docx**')).toBe('~/out/a.docx')
  })

  it('peels italic wrap around a path but keeps a trailing underscore filename', () => {
    expect(sanitizeFsPath('_~/out/a.docx_')).toBe('~/out/a.docx')
    expect(sanitizeFsPath('__/tmp/a.pdf__')).toBe('/tmp/a.pdf')
    expect(sanitizeFsPath('/tmp/a.docx_')).toBe('/tmp/a.docx')
    expect(sanitizeFsPath('/tmp/draft_')).toBe('/tmp/draft_')
    expect(sanitizeFsPath('/tmp/my_file.json')).toBe('/tmp/my_file.json')
  })

  it('leaves a clean path unchanged', () => {
    expect(sanitizeFsPath('/tmp/report.md')).toBe('/tmp/report.md')
    expect(sanitizeFsPath('C:/out/data.xlsx')).toBe('C:/out/data.xlsx')
  })
})
