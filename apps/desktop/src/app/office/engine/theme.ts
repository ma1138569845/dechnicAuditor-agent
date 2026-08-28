/**
 * 水墨主题配色 — 从 CSS 变量解析场景颜色，跟随 light/dark/comic 主题。
 * 语义色（在线/忙碌/离线）沿用主题的 --success/--warning/--text-muted；
 * agent 身份色用确定性灰阶明度区分（用户决策：黑白水墨下不用彩色区分 agent）。
 */

export interface OfficeThemeColors {
  floor: number
  floorDot: number
  deskSurface: number
  deskEdge: number
  monitor: number
  screen: number
  chair: number
  label: number
  statusOnline: number
  statusBusy: number
  statusOffline: number
  screenGlow: number
  bubbleBg: number
  bubbleBorder: number
  bubbleText: number
}

export function parseHexColor(value: string, fallback = '#808080'): number {
  const hex = String(value).trim().replace(/^#/, '')
  if (/^[0-9a-fA-F]{6}$/.test(hex)) return Number.parseInt(hex, 16)
  if (/^[0-9a-fA-F]{3}$/.test(hex)) {
    return Number.parseInt(hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2], 16)
  }
  return Number.parseInt(fallback.replace(/^#/, ''), 16)
}

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined' || typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

function hexVar(name: string, fallback: string): number {
  return parseHexColor(cssVar(name, fallback), fallback)
}

/** 读取当前主题下的全部场景颜色。 */
// Ported from hermes-studio-vue — CSS var names remapped to the desktop app's
// tokens (--ui-* surface/stroke/text + --ui-green/--ui-yellow semantics).
export function resolveSceneTheme(): OfficeThemeColors {
  return {
    floor: hexVar('--ui-bg-secondary', '#f0f0f0'),
    floorDot: hexVar('--ui-stroke-tertiary', '#e0e0e0'),
    deskSurface: hexVar('--ui-bg-card', '#ffffff'),
    deskEdge: hexVar('--ui-stroke-tertiary', '#e0e0e0'),
    monitor: hexVar('--ui-text-secondary', '#666666'),
    screen: hexVar('--ui-bg-primary', '#fafafa'),
    chair: hexVar('--ui-text-tertiary', '#999999'),
    label: hexVar('--ui-text-primary', '#1a1a1a'),
    statusOnline: hexVar('--ui-green', '#2e7d32'),
    statusBusy: hexVar('--ui-yellow', '#f57f17'),
    statusOffline: hexVar('--ui-text-tertiary', '#999999'),
    screenGlow: hexVar('--ui-yellow', '#f57f17'),
    bubbleBg: hexVar('--ui-bg-card', '#ffffff'),
    bubbleBorder: hexVar('--ui-stroke-tertiary', '#e0e0e0'),
    bubbleText: hexVar('--ui-text-primary', '#1a1a1a'),
  }
}

function nameHash(name: string): number {
  let h = 5381
  const s = String(name || '')
  for (let i = 0; i < s.length; i += 1) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0
  return h
}

function channel(from: number, to: number, fraction: number): number {
  return Math.round(from + (to - from) * fraction)
}

/**
 * 确定性灰阶 agent 身份色：在 --text-muted 与 --text-primary 之间按名字哈希插值，
 * 保证同一 agent 永远渲染同一种灰阶，且主题自适应（深色/浅色都可见）。
 */
export function agentColor(name: string): number {
  const from = hexVar('--ui-text-tertiary', '#999999')
  const to = hexVar('--ui-text-primary', '#1a1a1a')
  const fraction = 0.3 + ((nameHash(name) % 1000) / 1000) * 0.55 // 0.3 ~ 0.85，避开两端极值
  const r = channel((from >> 16) & 0xff, (to >> 16) & 0xff, fraction)
  const g = channel((from >> 8) & 0xff, (to >> 8) & 0xff, fraction)
  const b = channel(from & 0xff, to & 0xff, fraction)
  return (r << 16) | (g << 8) | b
}

/** 与 agent 灰阶色对比的文字色（头部首字母），保证浅色/深色角色上都可读。 */
export function contrastingTextColor(color: number): number {
  const r = (color >> 16) & 0xff
  const g = (color >> 8) & 0xff
  const b = color & 0xff
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.55 ? 0x1a1a1a : 0xffffff
}

/** DOM 降级网格使用的 CSS 灰阶色（与 Pixi 场景用同一确定性哈希）。 */
export function agentCssColor(name: string): string {
  return `#${agentColor(name).toString(16).padStart(6, '0')}`
}

/** 与 agent 灰阶色对比的 CSS 文字色（降级网格头部首字母）。 */
export function agentTextCssColor(name: string): string {
  const color = agentColor(name)
  const r = (color >> 16) & 0xff
  const g = (color >> 8) & 0xff
  const b = color & 0xff
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.55 ? '#1a1a1a' : '#ffffff'
}
