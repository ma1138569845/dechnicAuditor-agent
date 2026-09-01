/**
 * 办公室场景引擎 — Pixi Application + ticker 循环 + agent 对账。
 * 架构移植自 dechnic-auditor-agent-main（源自 ai-office-react-main src/scene/OfficeScene.ts：
 * ticker 循环、fit-stage 缩放、深度排序、ambient 自动拜访），适配 TypeScript + 动态 roster。
 */
import { Application, Container, FederatedPointerEvent, Graphics, Sprite } from 'pixi.js'

import { loadOfficeTextures, type OfficeTextures } from './assets'
import { DeskActor, AgentActor } from './characters'
import type { AgentRecord } from './characters'
import { SCENE_WIDTH, SCENE_HEIGHT, computeDesks, deskContentBounds } from './layout'
import type { SceneBounds } from './layout'
import { MissionRunner } from './missions'
import { resolveSceneTheme } from './theme'
import type { OfficeAction } from './types'

const AUTO_WORKFLOW_IDLE_SEC = 8

export interface OfficeAgentProfile {
  /** Canonical profile id — used for identity, clicks, cron matching. */
  name: string
  /** Presentation label (display_name when set). */
  label: string
  color: number
  online: boolean
  busy: boolean
  /** Short label of what the agent is working on (desk subtitle). */
  currentWork?: string | null
}

export interface OfficeSceneStrings {
  visitFallback: (hostName: string) => string
  ambientMessage: (visitorName: string, hostName: string) => string
}

export class OfficeSceneImpl {
  private app: Application | null = null
  private world: Container | null = null
  private mount: HTMLElement | null = null
  private contentBounds: SceneBounds = { x: 0, y: 0, w: SCENE_WIDTH, h: SCENE_HEIGHT }
  private textures: OfficeTextures | null = null
  private readonly agents = new Map<string, AgentRecord>()
  private readonly runner: MissionRunner
  private strings: OfficeSceneStrings
  private onAgentClick: ((payload: { name: string; clientX: number; clientY: number }) => void) | null = null
  private paused = true
  private idleTimer = 0
  private resizeObserver: ResizeObserver | null = null
  private readonly reducedMotion =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  constructor(strings: OfficeSceneStrings) {
    this.strings = strings
    this.runner = new MissionRunner(this.agents, {
      visitFallback: (host) => this.strings.visitFallback(host),
    })
    this.runner.reducedMotion = this.reducedMotion
  }

  async init(mount: HTMLElement, onAgentClick?: (payload: { name: string; clientX: number; clientY: number }) => void): Promise<boolean> {
    if (this.app) {
      this.onAgentClick = onAgentClick || this.onAgentClick
      return true
    }

    this.mount = mount
    const app = new Application()
    await app.init({
      background: resolveSceneTheme().floor,
      antialias: true,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
      resizeTo: mount
    })
    this.app = app
    mount.appendChild(app.canvas)
    app.canvas.style.display = 'block'

    this.onAgentClick = onAgentClick || null

    this.textures = await loadOfficeTextures()

    const world = new Container()
    this.world = world
    app.stage.addChild(world)

    this.drawFloor()
    this.fitStage()

    this.resizeObserver = new ResizeObserver(() => this.fitStage())
    this.resizeObserver.observe(mount)

    app.ticker.add(ticker => this.onTick(Math.min(ticker.deltaTime / 60, 0.05)))
    return true
  }

  private drawFloor(): void {
    const theme = resolveSceneTheme()
    const world = this.world!

    const bgTexture = this.textures?.background ?? null
    if (bgTexture) {
      const bg = new Sprite(bgTexture)
      const scale = Math.max(SCENE_WIDTH / bgTexture.width, SCENE_HEIGHT / bgTexture.height)
      bg.scale.set(scale)
      bg.position.set((SCENE_WIDTH - bgTexture.width * scale) / 2, (SCENE_HEIGHT - bgTexture.height * scale) / 2)
      bg.zIndex = -1000
      world.addChild(bg)
    } else {
      const floor = new Graphics()
      floor.rect(0, 0, SCENE_WIDTH, SCENE_HEIGHT).fill(theme.floor)
      // 点阵网格，镜像 DOM 降级网格的背景。
      for (let x = 40; x < SCENE_WIDTH; x += 88) {
        for (let y = 40; y < SCENE_HEIGHT; y += 88) {
          floor.circle(x, y, 2).fill({ color: theme.floorDot, alpha: 0.5 })
        }
      }
      floor.zIndex = -1000
      world.addChild(floor)
    }
  }

  /**
   * Zoom the world so the active desk cluster fills the mount (with padding),
   * instead of letterboxing the entire 1600×900 artboard and leaving a huge
   * empty ceiling. Caps scale so a single desk doesn't blow past the artboard.
   */
  private fitStage(): void {
    if (!this.app || !this.world || !this.mount) return
    const w = Math.max(1, this.mount.clientWidth || SCENE_WIDTH)
    const h = Math.max(1, this.mount.clientHeight || SCENE_HEIGHT)
    const bounds = this.contentBounds
    const letterbox = Math.min(w / SCENE_WIDTH, h / SCENE_HEIGHT)
    const cluster = Math.min(w / bounds.w, h / bounds.h)
    // Prefer the desk cluster crop, but never zoom in past ~1.35× letterbox —
    // extreme zoom makes the PNG background look tiled when the canvas overflows.
    const scale = Math.min(cluster, letterbox * 1.35)
    this.world.scale.set(scale)
    this.world.position.set(
      w / 2 - (bounds.x + bounds.w / 2) * scale,
      h / 2 - (bounds.y + bounds.h / 2) * scale
    )
    this.app.canvas.style.width = `${w}px`
    this.app.canvas.style.height = `${h}px`
    this.app.canvas.style.display = 'block'
  }

  /**
   * 用实时数据对账场景里的 agent。
   * @param profiles 场景角色列表
   */
  sync(profiles: OfficeAgentProfile[]): void {
    if (!this.app || !this.world) return
    const seen = new Set<string>()

    // 布局取决于 roster 大小 — 重新计算并重新入座。
    const desks = computeDesks(profiles.length)
    this.contentBounds = deskContentBounds(desks)
    this.fitStage()

    profiles.forEach((p, index) => {
      seen.add(p.name)
      const desk = desks[index]
      if (!desk) return
      let agent = this.agents.get(p.name)
      if (!agent) {
        agent = this.createAgent(p, desk)
        this.agents.set(p.name, agent)
      }
      if (agent.label !== p.label) {
        agent.label = p.label
        agent.deskActor.setLabel(p.label)
        agent.actor.setLabel(p.label)
      }
      agent.desk = desk
      agent.deskActor.desk = desk
      agent.deskActor.position.set(desk.x, desk.y)
      // Work-centric: busy → working, else idle-online (gateway is not desk presence).
      const base: AgentRecord['baseState'] = p.busy ? 'working' : 'online'
      agent.baseState = base
      agent.deskActor.setStatus(base)
      agent.deskActor.setTaskLabel(p.busy ? p.currentWork ?? null : null)
      agent.baseTask = p.busy ? p.currentWork ?? undefined : undefined
      if (!agent.mission && agent.state !== 'walking') {
        // 重新入座空闲 agent（覆盖 roster 变化后的工位移动）。
        agent.x = desk.seatX
        agent.y = desk.seatY
        agent.actor.position.set(agent.x, agent.y)
        agent.state = base
        agent.actor.setState(base)
      }
    })

    // 离开的 profile：移除 actor，丢弃任何涉及它的任务。
    for (const [name, agent] of [...this.agents]) {
      if (seen.has(name)) continue
      this.world.removeChild(agent.actor)
      this.world.removeChild(agent.deskActor)
      agent.actor.destroy({ children: true })
      agent.deskActor.destroy({ children: true })
      this.agents.delete(name)
    }
    for (const agent of this.agents.values()) {
      if (agent.mission && !this.agents.has(agent.mission.hostName)) {
        agent.mission = undefined
        agent.actor.hideBubble()
      }
    }
  }

  private createAgent(profile: OfficeAgentProfile, desk: ReturnType<typeof computeDesks>[number]): AgentRecord {
    const world = this.world!
    const label = profile.label || profile.name
    const deskActor = new DeskActor(desk, label, this.textures?.desk ?? null, this.textures?.chair ?? null)
    deskActor.position.set(desk.x, desk.y)
    deskActor.zIndex = desk.seatY - 20
    world.addChild(deskActor)

    const actor = new AgentActor(profile.name, profile.color, label)
    actor.position.set(desk.seatX, desk.seatY)
    actor.on('pointertap', (event: FederatedPointerEvent) => {
      this.onAgentClick?.({
        name: profile.name,
        clientX: event.clientX,
        clientY: event.clientY
      })
    })
    world.addChild(actor)

    const base: AgentRecord['baseState'] = profile.busy ? 'working' : 'online'
    const agent: AgentRecord = {
      name: profile.name,
      label,
      actor,
      deskActor,
      desk,
      x: desk.seatX,
      y: desk.seatY,
      state: base,
      baseState: base,
      targetX: undefined,
      targetY: undefined,
      walkPath: undefined,
      walkPathIndex: undefined,
      mission: undefined
    }
    actor.setState(base)
    deskActor.setTaskLabel(profile.busy ? profile.currentWork ?? null : null)
    agent.baseTask = profile.busy ? profile.currentWork ?? undefined : undefined
    return agent
  }

  enqueueAction(action: OfficeAction): boolean {
    this.idleTimer = 0
    return this.runner.enqueue(action)
  }

  playEmote(name: string, animation: string): boolean {
    const agent = this.agents.get(name)
    if (!agent) return false
    agent.actor.playEmote(animation)
    return true
  }

  get busy(): boolean {
    return this.runner.busy || this.runner.pending > 0
  }

  pause(): void {
    this.paused = true
    this.app?.ticker.stop()
  }

  resume(): void {
    if (!this.app) return
    this.paused = false
    this.idleTimer = 0
    this.app.ticker.start()
  }

  destroy(): void {
    this.resizeObserver?.disconnect()
    this.resizeObserver = null
    const mount = this.mount
    const canvas = this.app?.canvas
    this.app?.destroy(true, { children: true })
    this.app = null
    this.world = null
    this.mount = null
    this.agents.clear()
    // Pixi destroy should detach the canvas; remove orphans if a raced init left extras.
    if (canvas?.parentNode) canvas.parentNode.removeChild(canvas)
    if (mount) {
      for (const child of [...mount.querySelectorAll('canvas')]) {
        child.remove()
      }
    }
  }

  private onTick(dt: number): void {
    if (!this.world) return

    this.runner.tick(dt)

    for (const agent of this.agents.values()) {
      agent.actor.update(dt, this.reducedMotion)
      agent.deskActor.update(dt, this.reducedMotion)
      agent.actor.zIndex = agent.y
    }
    this.world.sortChildren()

    this.updateAutoWorkflow(dt)
  }

  /** 办公室空闲一段时间后触发 ambient 拜访 — AUTO_WORKFLOW 的移植。 */
  private updateAutoWorkflow(dt: number): void {
    if (this.reducedMotion || this.paused) return
    if (this.busy || typeof this.strings.ambientMessage !== 'function') {
      this.idleTimer = 0
      return
    }
    this.idleTimer += dt
    if (this.idleTimer < AUTO_WORKFLOW_IDLE_SEC) return

    const candidates = [...this.agents.values()].filter((a) => a.baseState !== 'offline')
    if (candidates.length < 2) {
      this.idleTimer = 0
      return
    }
    const visitor = candidates[Math.floor(Math.random() * candidates.length)]
    const hosts = candidates.filter((a) => a !== visitor)
    const host = hosts[Math.floor(Math.random() * hosts.length)]
    this.runner.enqueue({
      type: 'desk_visit',
      visitor: visitor.name,
      host: host.name,
      message: this.strings.ambientMessage(visitor.name, host.name),
    })
    this.idleTimer = 0
  }
}
