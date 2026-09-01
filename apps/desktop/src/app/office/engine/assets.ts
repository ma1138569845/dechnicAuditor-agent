// Office scene textures. Paths live under `public/assets/office/` and are
// copied into `dist/assets/office/` at build time. MUST go through
// `assetPath()` — root-absolute `/assets/...` breaks under Electron
// `file://` (resolves to the OS root, not the install dir).
import { Assets, type Texture } from 'pixi.js'

import { assetPath } from '@/lib/asset-path'

const BACKGROUND_URL = assetPath('assets/office/office.png')
const DESK_URL = assetPath('assets/office/desk.png')
const CHAIR_URL = assetPath('assets/office/chair.png')

export interface OfficeTextures {
  background: Texture | null
  desk: Texture | null
  chair: Texture | null
}

/**
 * Attempt to load the office PNG assets. Returns null textures on failure
 * so the engine can fall back to vector placeholders.
 */
export async function loadOfficeTextures(): Promise<OfficeTextures> {
  try {
    const [background, desk, chair] = await Promise.all([
      Assets.load<Texture>(BACKGROUND_URL),
      Assets.load<Texture>(DESK_URL),
      Assets.load<Texture>(CHAIR_URL),
    ])
    return { background, desk, chair }
  } catch {
    return { background: null, desk: null, chair: null }
  }
}
