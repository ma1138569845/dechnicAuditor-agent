/**
 * 对话气泡 — 移植自 ai-office-react-main src/scene/ui/Bubble.ts
 * （圆角矩形 + 尾巴 + 自动换行 + 定时淡出），行为保持一致。
 */
import { Container, Graphics, Text } from 'pixi.js'
import { resolveSceneTheme } from './theme'

export class Bubble extends Container {
  private readonly bg = new Graphics()
  private readonly messageText = new Text({ text: '', style: this.textStyle() })
  private lifetime = 0

  constructor() {
    super()
    this.messageText.anchor.set(0.5, 0.5)
    this.addChild(this.bg, this.messageText)
    this.visible = false
  }

  private textStyle() {
    const theme = resolveSceneTheme()
    return {
      fontFamily: 'system-ui, -apple-system, sans-serif',
      fontSize: 12,
      fill: theme.bubbleText,
      wordWrap: true,
      wordWrapWidth: 170,
      lineHeight: 16,
    }
  }

  show(text: string, duration = 4): void {
    this.messageText.text = String(text || '')
    this.lifetime = duration
    this.alpha = 1
    this.visible = true
    this.redraw()
  }

  hide(): void {
    this.visible = false
    this.lifetime = 0
  }

  /** @returns 仍可见 */
  update(dt: number): boolean {
    if (!this.visible) return false
    this.lifetime -= dt
    this.alpha = Math.min(1, this.lifetime / 0.5)
    if (this.lifetime <= 0) {
      this.hide()
      return false
    }
    return true
  }

  private redraw(): void {
    const theme = resolveSceneTheme()
    const padX = 10
    const padY = 7
    const w = this.messageText.width + padX * 2
    const h = this.messageText.height + padY * 2
    const r = 8
    const bodyTop = -h - 14

    this.bg.clear()
    this.bg.roundRect(-w / 2, bodyTop, w, h, r)
    this.bg.fill({ color: theme.bubbleBg, alpha: 0.96 })
    this.bg.stroke({ color: theme.bubbleBorder, width: 1 })

    // 尾巴
    this.bg.moveTo(-6, -14)
    this.bg.lineTo(0, -4)
    this.bg.lineTo(6, -14)
    this.bg.fill({ color: theme.bubbleBg, alpha: 0.96 })

    // 文本以气泡主体为中心（而非容器原点/尾巴尖端）。
    this.messageText.position.set(0, bodyTop + h / 2)
  }
}
