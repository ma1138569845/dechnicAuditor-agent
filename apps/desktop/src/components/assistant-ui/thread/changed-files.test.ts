import { describe, expect, it } from 'vitest'

import {
  deriveChangedFiles,
  formatChangedFileSize,
  isHtmlPath
} from '@/components/assistant-ui/thread/changed-files'
import { mediaMarkdownHref } from '@/lib/media'

const PATCH_DIFF = '--- a/src/demo.ts\n+++ b/src/demo.ts\n@@ -1 +1,2 @@\n-old\n+new\n+more\n'

function tool(partial: {
  args?: unknown
  isError?: boolean
  result?: unknown
  toolName: string
}) {
  return { type: 'tool-call', ...partial }
}

describe('deriveChangedFiles', () => {
  it('folds patch diffs into one row per path with +/- counts', () => {
    expect(
      deriveChangedFiles([
        tool({
          args: { path: 'src/demo.ts' },
          result: { diff: PATCH_DIFF, success: true },
          toolName: 'patch'
        })
      ])
    ).toEqual([{ added: 2, byteSize: undefined, name: 'demo.ts', path: 'src/demo.ts', removed: 1 }])
  })

  it('keeps a successful write_file create that has no persisted diff', () => {
    expect(
      deriveChangedFiles([
        tool({
          args: { content: 'hello', path: 'notes.md' },
          result: { bytes_written: 5 },
          toolName: 'write_file'
        })
      ])
    ).toEqual([{ added: 0, byteSize: 5, name: 'notes.md', path: 'notes.md', removed: 0 }])
  })

  it('skips running calls, failures, and non-edit tools', () => {
    expect(
      deriveChangedFiles([
        tool({ args: { path: 'a.ts' }, toolName: 'write_file' }),
        tool({
          args: { path: 'b.ts' },
          isError: true,
          result: { error: 'denied' },
          toolName: 'write_file'
        }),
        tool({
          args: { path: 'c.ts' },
          result: { success: false, error: 'conflict' },
          toolName: 'patch'
        }),
        tool({
          args: { path: 'README.md' },
          result: { content: '# hi' },
          toolName: 'read_file'
        })
      ])
    ).toEqual([])
  })

  it('keeps office_create and office_save paths as artifacts', () => {
    expect(
      deriveChangedFiles([
        tool({
          args: { doc_type: 'doc', file_path: 'C:/reports/audit.docx' },
          result: { file_path: 'C:/reports/audit.docx', success: true },
          toolName: 'office_create'
        }),
        tool({
          args: { file_id: 'new_doc_1', save_path: 'C:/out/data.xlsx' },
          result: { engine: 'editor_sdk', file_id: 'new_doc_1', success: true },
          toolName: 'office_save'
        })
      ])
    ).toEqual([
      { added: 0, byteSize: undefined, name: 'audit.docx', path: 'C:/reports/audit.docx', removed: 0 },
      { added: 0, byteSize: undefined, name: 'data.xlsx', path: 'C:/out/data.xlsx', removed: 0 }
    ])
  })

  it('ignores office_open and opaque editor file_ids', () => {
    expect(
      deriveChangedFiles([
        tool({
          args: { file_path: 'C:/reports/existing.docx' },
          result: { file_id: 'doc_1', file_path: 'C:/reports/existing.docx', success: true },
          toolName: 'office_open'
        }),
        tool({
          args: { file_id: 'new_doc_xxx' },
          result: { file_id: 'new_doc_xxx', success: true },
          toolName: 'office_save'
        })
      ])
    ).toEqual([])
  })

  it('keeps office files delivered via MEDIA in assistant text', () => {
    const path = 'C:/Users/Dechnic/projects/energy-audit/能源审计技能体系介绍.docx'
    const text = `文档已生成\n[File: 能源审计技能体系介绍.docx](${mediaMarkdownHref(path)})`

    expect(deriveChangedFiles([{ type: 'text', text }])).toEqual([
      { added: 0, byteSize: undefined, name: '能源审计技能体系介绍.docx', path, removed: 0 }
    ])
  })

  it('does not treat inline MEDIA images as file artifacts', () => {
    expect(
      deriveChangedFiles([
        { type: 'text', text: `[Image: shot.png](${mediaMarkdownHref('/tmp/shot.png')})` }
      ])
    ).toEqual([])
  })

  it('sums repeated edits to the same path and prefers the latest byte size', () => {
    const files = deriveChangedFiles([
      tool({
        args: { path: 'app.py' },
        result: { bytes_written: 10, success: true },
        toolName: 'write_file'
      }),
      tool({
        args: { path: 'app.py' },
        result: { diff: PATCH_DIFF, success: true },
        toolName: 'patch'
      }),
      tool({
        args: { content: 'updated', path: 'app.py' },
        result: { bytes_written: 7 },
        toolName: 'write_file'
      })
    ])

    expect(files).toEqual([{ added: 2, byteSize: 7, name: 'app.py', path: 'app.py', removed: 1 }])
  })
})

describe('formatChangedFileSize', () => {
  it('formats compact byte sizes and drops unknown values', () => {
    expect(formatChangedFileSize(undefined)).toBe('')
    expect(formatChangedFileSize(-1)).toBe('')
    expect(formatChangedFileSize(0)).toBe('0 B')
    expect(formatChangedFileSize(5)).toBe('5 B')
    expect(formatChangedFileSize(4915)).toBe('4.8 KB')
    expect(formatChangedFileSize(12 * 1024)).toBe('12 KB')
  })
})

describe('isHtmlPath', () => {
  it('recognizes html previews including query suffixes', () => {
    expect(isHtmlPath('cowriting_sidebar.html')).toBe(true)
    expect(isHtmlPath('index.htm')).toBe(true)
    expect(isHtmlPath('page.html?v=1')).toBe(true)
    expect(isHtmlPath('notes.md')).toBe(false)
  })
})
