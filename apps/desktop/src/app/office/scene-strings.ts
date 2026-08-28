import { translateNow } from '@/i18n'

import type { OfficeSceneStrings } from './engine/engine'

const AMBIENT_KEYS = ['office.ambient1', 'office.ambient2', 'office.ambient3', 'office.ambient4'] as const

/** Localized Pixi bubble copy — visit fallback + random ambient small-talk. */
export function officeSceneStrings(): OfficeSceneStrings {
  return {
    visitFallback: () => translateNow('office.visitFallback'),
    ambientMessage: () => {
      const key = AMBIENT_KEYS[Math.floor(Math.random() * AMBIENT_KEYS.length)]
      return translateNow(key)
    }
  }
}
