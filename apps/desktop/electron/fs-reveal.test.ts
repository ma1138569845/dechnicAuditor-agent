import path from 'node:path'

import { describe, expect, it, vi } from 'vitest'

import { revealPathForIpc, type RevealPathIo } from './fs-reveal'

function io(overrides: Partial<RevealPathIo> = {}): RevealPathIo {
  return {
    dirname: value => path.posix.dirname(value),
    existsSync: () => true,
    expandUserPath: value => value,
    normalize: value => value,
    openPath: vi.fn(async () => ''),
    showItemInFolder: vi.fn(),
    ...overrides
  }
}

describe('revealPathForIpc', () => {
  it('returns false for a missing or empty path without opening Explorer', async () => {
    const showItemInFolder = vi.fn()
    const openPath = vi.fn(async () => '')

    await expect(revealPathForIpc('  ', io({ openPath, showItemInFolder }))).resolves.toBe(false)
    await expect(revealPathForIpc('~/missing.docx', io({ existsSync: () => false, openPath, showItemInFolder }))).resolves.toBe(
      false
    )

    expect(showItemInFolder).not.toHaveBeenCalled()
    expect(openPath).not.toHaveBeenCalled()
  })

  it('expands ~ and selects the normalized Windows path', async () => {
    const showItemInFolder = vi.fn()
    const deps = io({
      expandUserPath: value => value.replace(/^~\//, 'C:/Users/me/'),
      normalize: value => path.win32.normalize(value),
      showItemInFolder
    })

    await expect(revealPathForIpc('~/projects/energy-audit/output/报告.docx', deps)).resolves.toBe(true)
    expect(showItemInFolder).toHaveBeenCalledWith('C:\\Users\\me\\projects\\energy-audit\\output\\报告.docx')
  })

  it('opens the parent folder when selecting the item throws', async () => {
    const openPath = vi.fn(async () => '')
    const deps = io({
      dirname: value => path.win32.dirname(value),
      normalize: value => path.win32.normalize(value),
      openPath,
      showItemInFolder: () => {
        throw new Error('Explorer rejected the select')
      }
    })

    await expect(revealPathForIpc('C:/out/报告.docx', deps)).resolves.toBe(true)
    expect(openPath).toHaveBeenCalledWith('C:\\out')
  })

  it('returns false when the parent-folder fallback also fails', async () => {
    const deps = io({
      openPath: async () => 'Failed to open',
      showItemInFolder: () => {
        throw new Error('Explorer rejected the select')
      }
    })

    await expect(revealPathForIpc('/tmp/report.docx', deps)).resolves.toBe(false)
  })
})
