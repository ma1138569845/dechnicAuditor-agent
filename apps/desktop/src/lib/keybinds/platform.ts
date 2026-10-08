/** Cmd vs Ctrl host. Leaf module so combo.ts and actions.ts do not cycle. */
export const IS_MAC =
  typeof navigator !== 'undefined' && /mac/i.test(navigator.platform || navigator.userAgent || '')
