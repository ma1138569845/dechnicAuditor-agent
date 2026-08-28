/** Right floating panel width — keep in sync with layout `pe-[calc(...)]` insets. */
export const OFFICE_PANEL_W = 'w-60' // 15rem — compact so desks stay in view

/**
 * Shared glass treatment for office chrome floating over the Pixi scene.
 * Lighter fill + stronger blur so the room reads through the UI seams.
 */
export const OFFICE_GLASS = [
  'border border-[color-mix(in_srgb,var(--stroke-nous)_36%,transparent)]',
  'bg-[color-mix(in_srgb,var(--ui-bg-elevated)_38%,transparent)]',
  'shadow-[0_0.5rem_1.5rem_color-mix(in_srgb,#000_10%,transparent),inset_0_1px_0_color-mix(in_srgb,#fff_8%,transparent)]',
  'backdrop-blur-2xl'
].join(' ')
