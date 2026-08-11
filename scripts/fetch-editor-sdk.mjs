#!/usr/bin/env node
// Fetch the editor_sdk binary from a release asset at build time.
//
// The binary is ~177 MB, which exceeds GitHub's 100 MB plain-git limit, so it
// is distributed as a GitHub Release attachment instead of a git blob. This
// script is invoked during `npm run build` and is idempotent: if the binary
// already exists and its SHA256 matches, it exits immediately.
//
// Override defaults via environment variables:
//   EDITOR_SDK_URL      - full download URL
//   EDITOR_SDK_SHA256   - expected SHA256 hex digest
//   EDITOR_SDK_DEST     - destination path (default: bin/editor_sdk.exe)

import { createHash } from 'node:crypto'
import { createWriteStream, existsSync } from 'node:fs'
import { mkdir, readFile, rm } from 'node:fs/promises'
import path from 'node:path'
import { Readable } from 'node:stream'
import { finished } from 'node:stream/promises'

const DEFAULT_URL =
  'https://github.com/ma1138569845/dechnicAuditor-agent/releases/download/editor-sdk-v1.0.0/editor_sdk.exe'
const DEFAULT_SHA256 = '4ad3f7db29975c7c7a67d6ced7f95c97712fc458f81c1773d9343373d790fc82'
const DEFAULT_DEST = path.resolve(import.meta.dirname, '..', 'bin', 'editor_sdk.exe')

const url = process.env.EDITOR_SDK_URL || DEFAULT_URL
const expectedSha256 = (process.env.EDITOR_SDK_SHA256 || DEFAULT_SHA256).toLowerCase()
const dest = path.resolve(process.env.EDITOR_SDK_DEST || DEFAULT_DEST)

async function sha256File(filePath) {
  const data = await readFile(filePath)
  return createHash('sha256').update(data).digest('hex')
}

async function main() {
  if (existsSync(dest)) {
    try {
      const actual = await sha256File(dest)
      if (actual === expectedSha256) {
        console.log('[fetch-editor-sdk] editor_sdk.exe already present and verified')
        return
      }
      console.warn(`[fetch-editor-sdk] existing file hash mismatch (expected ${expectedSha256}, got ${actual}); re-downloading`)
      await rm(dest, { force: true })
    } catch (error) {
      console.warn('[fetch-editor-sdk] failed to verify existing file:', error.message)
      await rm(dest, { force: true })
    }
  }

  console.log('[fetch-editor-sdk] downloading from', url)
  await mkdir(path.dirname(dest), { recursive: true })

  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`download failed: ${res.status} ${res.statusText} (${url})`)
  }

  const fileStream = createWriteStream(dest)
  try {
    await finished(Readable.fromWeb(res.body).pipe(fileStream))
  } catch (error) {
    await rm(dest, { force: true })
    throw new Error(`download stream failed: ${error.message}`)
  }

  const actual = await sha256File(dest)
  if (actual !== expectedSha256) {
    await rm(dest, { force: true })
    throw new Error(`sha256 mismatch: expected ${expectedSha256}, got ${actual}`)
  }

  console.log('[fetch-editor-sdk] downloaded and verified:', dest)
}

main().catch(error => {
  console.error('[fetch-editor-sdk]', error.message)
  process.exit(1)
})
