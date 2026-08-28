// Ported from hermes-studio-vue `packages/client/src/components/hermes/office/office-scene/assets.ts`.
// Asset paths already match the desktop app's `public/assets/office/` layout.
import { Assets, Texture } from 'pixi.js'

const BACKGROUND_URL = '/assets/office/office.png'
const DESK_URL = '/assets/office/desk.png'
const CHAIR_URL = '/assets/office/chair.png'

let backgroundTexture: Texture | null = null
let deskTexture: Texture | null = null
let chairTexture: Texture | null = null

export async function loadOfficeTextures(): Promise<boolean> {
  try {
    Assets.add({ alias: 'office-bg', src: BACKGROUND_URL })
    Assets.add({ alias: 'office-desk', src: DESK_URL })
    Assets.add({ alias: 'office-chair', src: CHAIR_URL })
    const [bg, desk, chair] = await Promise.all([
      Assets.load<Texture>('office-bg'),
      Assets.load<Texture>('office-desk'),
      Assets.load<Texture>('office-chair'),
    ])
    backgroundTexture = bg ?? null
    deskTexture = desk ?? null
    chairTexture = chair ?? null
    return !!(deskTexture && chairTexture)
  } catch (err) {
    console.warn('[OfficeScene] failed to load PNG textures', err)
    return false
  }
}

export function getOfficeBackgroundTexture(): Texture | null {
  return backgroundTexture
}

export function getOfficeDeskTexture(): Texture | null {
  return deskTexture
}

export function getOfficeChairTexture(): Texture | null {
  return chairTexture
}
