import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $notifications, clearNotifications } from '@/store/notifications'

vi.mock('@/lib/media', () => ({
  downloadGatewayMediaFile: vi.fn()
}))

vi.mock('@/lib/desktop-fs', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/desktop-fs')>()

  return { ...actual, revealDesktopPath: vi.fn() }
})

const media = await import('@/lib/media')
const downloadGatewayMediaFile = vi.mocked(media.downloadGatewayMediaFile)
const desktopFs = await import('@/lib/desktop-fs')
const revealDesktopPath = vi.mocked(desktopFs.revealDesktopPath)

const { downloadRemoteFile, revealFile, shouldOfferRemoteFileDownload } = await import('./file-actions')

describe('shouldOfferRemoteFileDownload', () => {
  it('is only for files on a remote backend', () => {
    expect(shouldOfferRemoteFileDownload(false, true)).toBe(true)
    expect(shouldOfferRemoteFileDownload(true, true)).toBe(false)
    expect(shouldOfferRemoteFileDownload(false, false)).toBe(false)
    expect(shouldOfferRemoteFileDownload(true, false)).toBe(false)
  })
})

describe('revealFile', () => {
  beforeEach(() => {
    clearNotifications()
    revealDesktopPath.mockReset()
  })

  afterEach(() => {
    clearNotifications()
  })

  it('stays quiet when the OS file manager reveals the path', async () => {
    revealDesktopPath.mockResolvedValue(true)

    await revealFile('C:/out/报告.docx')

    expect(revealDesktopPath).toHaveBeenCalledWith('C:/out/报告.docx')
    expect($notifications.get()).toEqual([])
  })

  it('toasts reveal copy when the main process cannot show the file', async () => {
    revealDesktopPath.mockResolvedValue(false)

    await revealFile('~/projects/energy-audit/output/报告.docx')

    expect($notifications.get()[0]?.kind).toBe('error')
    expect($notifications.get()[0]?.title).toBe('Could not reveal the file')
    expect($notifications.get()[0]?.message).toBe('Could not reveal the file')
  })
})

describe('downloadRemoteFile', () => {
  beforeEach(() => {
    clearNotifications()
    downloadGatewayMediaFile.mockReset()
  })

  afterEach(() => {
    clearNotifications()
  })

  it('saves a remote gateway file through the native download bridge', async () => {
    downloadGatewayMediaFile.mockResolvedValue({ path: '/Users/me/Downloads/notes.md', saved: true })

    await downloadRemoteFile('/home/linux/project/notes.md')

    expect(downloadGatewayMediaFile).toHaveBeenCalledWith('/home/linux/project/notes.md')
    expect($notifications.get()[0]?.message).toBe('Saved')
  })

  it('stays quiet when the save dialog is canceled', async () => {
    downloadGatewayMediaFile.mockResolvedValue({ canceled: true, saved: false })

    await downloadRemoteFile('/home/linux/project/notes.md')

    expect($notifications.get()).toEqual([])
  })

  it('toasts when the gateway download fails', async () => {
    downloadGatewayMediaFile.mockRejectedValue(new Error('Desktop file download bridge is unavailable'))

    await downloadRemoteFile('/home/linux/project/notes.md')

    expect($notifications.get()[0]?.kind).toBe('error')
    expect($notifications.get()[0]?.title).toBe('Download failed')
  })
})
