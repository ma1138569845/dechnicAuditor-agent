/**
 * 办公室场景布局 — 为 N 个 profile 动态排布工位。
 * 概念移植自 dechnic-auditor-agent-main（源自 ai-office-react-main src/scene/layout/officeLayout.ts），
 * 适配动态 roster（hermes profiles 不是固定的 6-agent 阵容）。
 */

export const SCENE_WIDTH = 1600
export const SCENE_HEIGHT = 900

/** 工位尺寸（px）— 与 characters.ts 里矢量绘制保持一致。 */
export const DESK_W = 200
export const DESK_H = 150

const MARGIN_X = 150
const ROW_GAP = 260
const MAX_COLS = 4
/** 避开背景图天花 / 前景装饰的可用竖向带。 */
const USABLE_TOP = 200
const USABLE_BOTTOM = SCENE_HEIGHT - 100

export interface Point {
  x: number
  y: number
}

export interface DeskLayout {
  id: string
  x: number
  y: number
  seatX: number
  seatY: number
  row: number
}

export interface SceneBounds {
  x: number
  y: number
  w: number
  h: number
}

/**
 * 在居中网格中排布 `count` 个工位（每行最多 MAX_COLS 个）。
 * 整块工位在可用竖向带内垂直居中，避免贴顶留下大片空天花。
 * 返回 [{ id, x, y, seatX, seatY, row }] — (x,y) 是工位中心，
 * (seatX,seatY) 是角色站立锚点。
 */
export function computeDesks(count: number): DeskLayout[] {
  if (count <= 0) return []
  const cols = Math.min(count, MAX_COLS)
  const rows = Math.ceil(count / cols)
  const blockHeight = (rows - 1) * ROW_GAP + DESK_H
  const usableHeight = USABLE_BOTTOM - USABLE_TOP
  const blockTop = USABLE_TOP + Math.max(0, (usableHeight - blockHeight) / 2)

  const desks: DeskLayout[] = []
  for (let r = 0; r < rows; r += 1) {
    const inRow = r === rows - 1 ? count - r * cols : cols
    const rowWidth = inRow * DESK_W + (inRow - 1) * 60
    const startX = (SCENE_WIDTH - rowWidth) / 2 + DESK_W / 2
    const y = blockTop + r * ROW_GAP + DESK_H / 2
    for (let c = 0; c < inRow; c += 1) {
      const x = Math.max(MARGIN_X, Math.min(SCENE_WIDTH - MARGIN_X, startX + c * (DESK_W + 60)))
      desks.push({
        id: `desk-${r * cols + c}`,
        x,
        y,
        seatX: x,
        seatY: y + DESK_H / 2 - 30,
        row: r
      })
    }
  }
  return desks
}

/** 工位 + 角色头像/铭牌的包围盒，供 fitStage 裁切空白。 */
export function deskContentBounds(desks: DeskLayout[]): SceneBounds {
  if (desks.length === 0) {
    return { x: 0, y: 0, w: SCENE_WIDTH, h: SCENE_HEIGHT }
  }

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const desk of desks) {
    minX = Math.min(minX, desk.x - DESK_W / 2)
    maxX = Math.max(maxX, desk.x + DESK_W / 2)
    // Avatar sits above the desk; label sits below.
    minY = Math.min(minY, desk.y - DESK_H / 2 - 80)
    maxY = Math.max(maxY, desk.y + DESK_H / 2 + 50)
  }

  const padX = 140
  const padY = 110
  const x = Math.max(0, minX - padX)
  const y = Math.max(0, minY - padY)
  const right = Math.min(SCENE_WIDTH, maxX + padX)
  const bottom = Math.min(SCENE_HEIGHT, maxY + padY)

  return { x, y, w: Math.max(1, right - x), h: Math.max(1, bottom - y) }
}

/**
 * 两个点之间的 L 形走廊路径：先下到 aisle 车道、横向走、再接近目标。
 * 源自参考实现的 nav 几何意图（aisle-first routing），简化版——本场景走廊间无障碍。
 */
export function planPath(fromX: number, fromY: number, toX: number, toY: number): Point[] {
  const aisleY = Math.max(fromY, toY) + 110
  const clamped = Math.min(aisleY, SCENE_HEIGHT - 90)
  const path: Point[] = []
  if (Math.abs(fromY - toY) > 8 || Math.abs(fromX - toX) > 8) {
    path.push({ x: fromX, y: clamped })
    path.push({ x: toX, y: clamped })
  }
  path.push({ x: toX, y: toY })
  return path
}

/** 访客站到 host 工位旁（走廊一侧）的位置。 */
export function visitSpotFor(hostSeatX: number, hostSeatY: number, visitorX: number): Point {
  const side = visitorX <= hostSeatX ? -1 : 1
  return { x: hostSeatX + side * 95, y: hostSeatY + 55 }
}
