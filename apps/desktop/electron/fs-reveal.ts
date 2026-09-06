// Pure reveal helper for `hermes:fs:reveal`. Electron's
// `shell.showItemInFolder` silently no-ops on a missing path and, on Windows,
// on an existing path that still has POSIX slashes. Normalize first; if the
// select call throws, open the parent folder so the user still gets a window.

export interface RevealPathIo {
  dirname: (value: string) => string
  existsSync: (value: string) => boolean
  expandUserPath: (value: string) => string
  normalize: (value: string) => string
  openPath: (value: string) => Promise<string>
  showItemInFolder: (value: string) => void
}

export async function revealPathForIpc(rawPath: unknown, io: RevealPathIo): Promise<boolean> {
  const target = io.expandUserPath(String(rawPath || '').trim())

  if (!target || !io.existsSync(target)) {
    return false
  }

  const normalized = io.normalize(target)

  try {
    io.showItemInFolder(normalized)

    return true
  } catch {
    const error = await io.openPath(io.dirname(normalized))

    return !error
  }
}
