import { describe, expect, it } from 'vitest'

import { clampMenuPosition, MENU_MAX_HEIGHT, MENU_WIDTH, VIEWPORT_MARGIN } from './menu-position'

describe('clampMenuPosition', () => {
  it('keeps the click point when the menu fits', () => {
    expect(clampMenuPosition(100, 80, 1200, 800)).toEqual({ left: 100, top: 80 })
  })

  it('shifts left when overflowing the right edge', () => {
    const { left } = clampMenuPosition(1100, 80, 1200, 800)
    expect(left).toBe(1200 - MENU_WIDTH - VIEWPORT_MARGIN)
  })

  it('flips upward when overflowing the bottom edge', () => {
    const { top } = clampMenuPosition(100, 700, 1200, 800)
    expect(top).toBe(Math.max(VIEWPORT_MARGIN, 700 - MENU_MAX_HEIGHT - VIEWPORT_MARGIN))
  })
})
