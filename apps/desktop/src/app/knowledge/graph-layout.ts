export const INSPECTOR_DEFAULT_PX = 320
export const INSPECTOR_MIN_PX = 220
export const INSPECTOR_MAX_PX = 560
export const GRAPH_CANVAS_MIN_PX = 240

export function clampInspectorWidth(width: number, splitWidth: number): number {
  const max = Math.min(INSPECTOR_MAX_PX, Math.max(INSPECTOR_MIN_PX, splitWidth - GRAPH_CANVAS_MIN_PX))

  return Math.round(Math.min(Math.max(width, INSPECTOR_MIN_PX), max))
}
