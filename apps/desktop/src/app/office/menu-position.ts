/** Viewport-clamp for the floating agent action menu (ported from Vue OfficeAgentActionMenu). */

export const MENU_WIDTH = 220
export const MENU_MAX_HEIGHT = 460
export const VIEWPORT_MARGIN = 12

export function clampMenuPosition(
  x: number,
  y: number,
  vw: number,
  vh: number,
  width = MENU_WIDTH,
  maxHeight = MENU_MAX_HEIGHT,
  margin = VIEWPORT_MARGIN
): { left: number; top: number } {
  let left = x
  let top = y
  if (left + width + margin > vw) {
    left = Math.max(margin, vw - width - margin)
  }
  if (top + maxHeight + margin > vh) {
    top = Math.max(margin, top - maxHeight - margin)
  }
  return { left, top }
}
