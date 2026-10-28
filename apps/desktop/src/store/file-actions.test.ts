import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $notifications, clearNotifications } from '@/store/notifications'

vi.mock('@/lib/media', () => ({
  downloadGatewayFileWithFeedback: vi.fn()
}))

vi.mock('@/lib/desktop-fs', async importOriginal => {
  const actual = (await importOriginal()) as Record<string, unknown>

  return { ...actual, revealDesktopPath: vi.fn() }
})

const media = await import('@/lib/media')
const downloadGatewayFileWithFeedback = vi.mocked(media.downloadGatewayFileWithFeedback)
const desktopFs = await import('@/lib/desktop-fs')
const revealDesktopPath = vi.mocked(desktopFs.revealDesktopPath)

const { downloadRemoteFile, revealFile, shouldOfferLocalReveal, shouldOfferRemoteFileDownload } = await import('./file-actions')

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

describe('shouldOfferLocalReveal', () => {
  // The OS file manager can only show what is on this computer (#115167): the
  // focused row's backend decides; the primary's mode only when it is untagged.
  it.each([
    ['', false, true],
    ['', true, false],
    ['local', true, true],
    ['mini', false, false],
    [undefined, true, false]
  ])('connection %s with primaryRemote=%s -> %s', (connectionId, primaryRemote, expected) => {
    expect(shouldOfferLocalReveal(connectionId, primaryRemote)).toBe(expected)
  })
})

describe('downloadRemoteFile', () => {
  beforeEach(() => {
    downloadGatewayFileWithFeedback.mockReset()
  })

  it('uses the shared gateway download flow', async () => {
    downloadGatewayFileWithFeedback.mockResolvedValue(undefined)

    await downloadRemoteFile('/home/linux/project/notes.md')

    expect(downloadGatewayFileWithFeedback).toHaveBeenCalledWith('/home/linux/project/notes.md')
  })
})
