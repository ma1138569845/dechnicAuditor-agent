/**
 * 矢量办公室角色（工位 + chibi 角色），用 Pixi Graphics 绘制。
 * 视觉语言对应 DOM 降级网格的 CSS 工位卡片（桌面/显示器/椅子 + 头部首字母角色）。
 * 参考项目的 Spine/chibi 资源刻意不用（版权 + 专有运行时）。
 */
import { Container, Graphics, Sprite, Text } from 'pixi.js'
import type { TextStyleOptions } from 'pixi.js'
import { Bubble } from './bubbles'
import { resolveSceneTheme, contrastingTextColor } from './theme'
import { DESK_W, DESK_H } from './layout'
import type { DeskLayout, Point } from './layout'
import { getOfficeDeskTexture, getOfficeChairTexture } from './assets'

export type DeskStatus = 'working' | 'online' | 'offline'
export type BaseState = 'working' | 'online' | 'offline' | 'thinking'
/** 含 'idle' 作为到达途经点后的瞬时标记（任务 FSM 下帧重新标记）。 */
export type AgentState = BaseState | 'walking' | 'talking' | 'idle'

export interface MissionStop {
  host: string
  message: string
}

export interface Mission {
  phase: 'goto' | 'talk' | 'return'
  hostName: string
  message: string
  talkDuration: number
  talkRemaining?: number
  queue: MissionStop[]
}

export interface AgentRecord {
  name: string
  actor: AgentActor
  deskActor: DeskActor
  desk: DeskLayout
  x: number
  y: number
  state: AgentState
  baseState: BaseState
  baseTask?: string
  targetX?: number
  targetY?: number
  walkPath?: Point[]
  walkPathIndex?: number
  mission?: Mission
}

const LABEL_STYLE: TextStyleOptions = {
  fontFamily: 'system-ui, -apple-system, sans-serif',
  fontSize: 13,
  fontWeight: '600',
}

const INITIAL_STYLE: TextStyleOptions = {
  fontFamily: 'system-ui, -apple-system, sans-serif',
  fontSize: 15,
  fontWeight: '700',
}

/** 静态工位：台面、显示器、椅子、名字、状态点。 */
export class DeskActor extends Container {
  desk: DeskLayout

  private readonly theme = resolveSceneTheme()
  private readonly screenGlow = new Graphics()
  private readonly statusDot = new Graphics()

  constructor(desk: DeskLayout, name: string) {
    super()
    this.desk = desk

    const deskTexture = getOfficeDeskTexture()
    const chairTexture = getOfficeChairTexture()
    const hasTextures = !!(deskTexture && chairTexture)

    const g = new Graphics()
    // 阴影
    g.ellipse(0, 58, 78, 12).fill({ color: 0x000000, alpha: 0.12 })
    // 台面
    g.roundRect(-88, -30, 176, 84, 12).fill(this.theme.deskSurface).stroke({ color: this.theme.deskEdge, width: 2 })
    // 显示器 + 底座
    g.roundRect(-26, -62, 52, 34, 4).fill(this.theme.monitor)
    g.roundRect(-21, -57, 42, 24, 2).fill(this.theme.screen)
    g.rect(-3, -28, 6, 8).fill(this.theme.monitor)
    // 椅子（座位点后方）
    g.roundRect(-16, 30, 32, 18, 5).fill(this.theme.chair).stroke({ color: 0x9d9688, width: 1 })
    g.visible = !hasTextures
    this.addChild(g)

    if (deskTexture) {
      const deskSprite = new Sprite(deskTexture)
      deskSprite.anchor.set(0.5, 0.5)
      const scale = Math.min(DESK_W / deskTexture.width, DESK_H / deskTexture.height)
      deskSprite.scale.set(scale)
      deskSprite.position.set(0, 10)
      this.addChild(deskSprite)
    }

    if (chairTexture) {
      const chairSprite = new Sprite(chairTexture)
      chairSprite.anchor.set(0.5, 0.5)
      const scale = Math.min(64 / chairTexture.width, 64 / chairTexture.height)
      chairSprite.scale.set(scale)
      chairSprite.position.set(0, 56)
      this.addChild(chairSprite)
    }

    this.screenGlow.roundRect(-21, -57, 42, 24, 2).fill({ color: this.theme.screenGlow, alpha: 0 })
    this.addChild(this.screenGlow)

    this.addChild(this.statusDot)

    const label = new Text({ text: name, style: { ...LABEL_STYLE, fill: this.theme.label } })
    label.anchor.set(0.5, 0)
    label.position.set(0, 72)
    this.addChild(label)

    this.setStatus('offline')
  }

  setStatus(status: DeskStatus): void {
    const dotColor = status === 'working' ? this.theme.statusBusy : status === 'online' ? this.theme.statusOnline : this.theme.statusOffline
    this.statusDot.clear()
    if (status === 'offline') {
      // 离线：空心灰点
      this.statusDot.circle(72, -18, 5).stroke({ color: dotColor, width: 1.5 })
    } else {
      this.statusDot.circle(72, -18, 5).fill(dotColor).stroke({ color: 0xffffff, width: 1.5 })
    }
    this.screenGlow.alpha = status === 'working' ? 0.85 : 0
    this.alpha = status === 'offline' ? 0.6 : 1
  }
}

/**
 * 可移动 chibi 角色。原点 = 脚底锚点。座位点是工位的 (seatX, seatY)；
 * 行走时整个容器移动。
 */
export class AgentActor extends Container {
  agentName: string
  state: AgentState = 'online'
  celebrating = 0

  private readonly body: Container
  private readonly shadow: Graphics
  private readonly bubble: Bubble
  private readonly head: Container
  private readonly torso: Graphics
  private readonly leftArm: Graphics
  private readonly rightArm: Graphics
  private readonly leftLeg: Graphics
  private readonly rightLeg: Graphics
  private readonly thinkingDots: Container

  private bobPhase = Math.random() * Math.PI * 2
  private customAnimation: string | null = null
  private customAnimTimer = 0

  constructor(name: string, color: number) {
    super()
    this.agentName = name

    this.shadow = new Graphics()
    this.shadow.ellipse(0, 4, 24, 7).fill({ color: 0x000000, alpha: 0.2 })
    this.addChild(this.shadow)

    this.body = new Container()
    this.addChild(this.body)

    this.torso = new Graphics()
    this.torso.roundRect(-15, -50, 30, 30, 10).fill(color)
    this.body.addChild(this.torso)

    this.leftLeg = new Graphics()
    this.leftLeg.roundRect(-4, 0, 8, 22, 4).fill(color)
    this.leftLeg.position.set(-7, -24)
    this.body.addChild(this.leftLeg)

    this.rightLeg = new Graphics()
    this.rightLeg.roundRect(-4, 0, 8, 22, 4).fill(color)
    this.rightLeg.position.set(7, -24)
    this.body.addChild(this.rightLeg)

    this.leftArm = new Graphics()
    this.leftArm.roundRect(-3, 0, 6, 20, 3).fill(color)
    this.leftArm.position.set(-18, -46)
    this.body.addChild(this.leftArm)

    this.rightArm = new Graphics()
    this.rightArm.roundRect(-3, 0, 6, 20, 3).fill(color)
    this.rightArm.position.set(18, -46)
    this.body.addChild(this.rightArm)

    this.head = new Container()
    const skull = new Graphics()
    skull.circle(0, 0, 16).fill(color)
    skull.circle(-5, -6, 5).fill({ color: 0xffffff, alpha: 0.25 })
    this.head.addChild(skull)
    const initial = new Text({
      text: (name || '?').trim().charAt(0).toUpperCase() || '?',
      style: { ...INITIAL_STYLE, fill: contrastingTextColor(color) },
    })
    initial.anchor.set(0.5, 0.5)
    this.head.addChild(initial)
    this.head.position.set(0, -62)
    this.body.addChild(this.head)

    this.thinkingDots = new Container()
    for (let i = 0; i < 3; i += 1) {
      const dot = new Graphics()
      dot.circle(i * 8 - 8, 0, 3).fill({ color: 0xffffff, alpha: 0.85 })
      this.thinkingDots.addChild(dot)
    }
    this.thinkingDots.position.set(0, -88)
    this.thinkingDots.visible = false
    this.body.addChild(this.thinkingDots)

    this.bubble = new Bubble()
    this.bubble.position.set(0, -104)
    this.addChild(this.bubble)

    this.eventMode = 'static'
    this.cursor = 'pointer'
  }

  setState(state: AgentState): void {
    this.state = state
    this.body.alpha = state === 'offline' ? 0.5 : 1
    this.resetPose()
  }

  /** @param dir 1 | -1 — 行走/交谈时水平翻转 */
  setFacing(dir: number): void {
    this.body.scale.x = dir >= 0 ? 1 : -1
  }

  showBubble(text: string, duration = 4): void {
    this.bubble.show(text, duration)
  }

  hideBubble(): void {
    this.bubble.hide()
  }

  /** 短促的 squash-stretch 弹跳（任务完成）。 */
  celebrate(): void {
    this.celebrating = 0.9
  }

  playEmote(animation: string): void {
    this.customAnimation = animation
    this.customAnimTimer = 2
    this.resetPose()
  }

  private resetPose(): void {
    this.leftArm.rotation = 0
    this.rightArm.rotation = 0
    this.leftLeg.rotation = 0
    this.rightLeg.rotation = 0
    this.body.position.y = 0
    this.body.scale.y = 1
    this.thinkingDots.visible = false
  }

  /** 每帧动画。 */
  update(dt: number, reducedMotion: boolean): void {
    this.bubble.update(dt)

    if (this.celebrating > 0) {
      this.celebrating -= dt
      const p = Math.max(0, this.celebrating) / 0.9
      const hop = Math.sin(p * Math.PI * 3) * 10 * p
      this.body.position.y = -Math.abs(hop)
      this.body.scale.y = 1 + Math.sin(p * Math.PI * 3) * 0.12 * p
      if (this.celebrating <= 0) {
        this.resetPose()
      }
      return
    }

    if (reducedMotion || this.state === 'offline') {
      this.resetPose()
      return
    }

    if (this.customAnimTimer > 0) {
      this.customAnimTimer -= dt
      this.applyCustomAnimation(dt)
      if (this.customAnimTimer <= 0) {
        this.customAnimation = null
      }
      return
    }

    this.bobPhase += dt * (this.state === 'walking' ? 11 : this.state === 'working' || this.state === 'talking' ? 5 : 2)
    const amp = this.state === 'walking' ? 2.5 : this.state === 'working' || this.state === 'talking' ? 1.6 : 0.7
    this.body.position.y = Math.sin(this.bobPhase) * -amp

    this.resetPose()
    this.body.position.y = Math.sin(this.bobPhase) * -amp

    if (this.state === 'walking') {
      const swing = Math.sin(this.bobPhase) * 0.5
      this.leftArm.rotation = -swing
      this.rightArm.rotation = swing
      this.leftLeg.rotation = swing * 0.6
      this.rightLeg.rotation = -swing * 0.6
    } else if (this.state === 'working') {
      const type = Math.sin(this.bobPhase * 2) * 0.15
      this.leftArm.rotation = -0.3 + type
      this.rightArm.rotation = 0.3 - type
    } else if (this.state === 'thinking') {
      this.thinkingDots.visible = true
      this.thinkingDots.position.y = -88 + Math.sin(this.bobPhase * 2) * 2
    }
  }

  private applyCustomAnimation(dt: number): void {
    this.bobPhase += dt * 8
    const anim = this.customAnimation ?? ''

    if (anim === 'emotes/wave') {
      this.body.position.y = Math.sin(this.bobPhase) * -1
      this.rightArm.rotation = -Math.PI / 2 + Math.sin(this.bobPhase * 3) * 0.5
      this.leftArm.rotation = 0
    } else if (anim === 'emotes/determined') {
      this.leftArm.rotation = -Math.PI / 1.3
      this.rightArm.rotation = Math.PI / 1.3
      this.body.scale.y = 1 + Math.sin(this.bobPhase) * 0.03
    } else if (anim === 'emotes/thinking') {
      this.thinkingDots.visible = true
      this.thinkingDots.position.y = -90 + Math.sin(this.bobPhase) * 2
      this.leftArm.rotation = -0.6
      this.rightArm.rotation = 0.6
    } else if (anim === 'emotes/excited') {
      const hop = Math.abs(Math.sin(this.bobPhase * 2)) * 10
      this.body.position.y = -hop
      this.leftArm.rotation = -Math.PI / 1.2
      this.rightArm.rotation = Math.PI / 1.2
    }
  }
}
