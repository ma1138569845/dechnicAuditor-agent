/**
 * 办公室场景引擎 — Pixi Application + ticker 循环 + agent 对账。
 * 架构移植自 dechnic-auditor-agent-main（源自 ai-office-react-main src/scene/OfficeScene.ts：
 * ticker 循环、fit-stage 缩放、深度排序、ambient 自动拜访），适配 TypeScript + 动态 roster。
 */
import { Application, Container, FederatedPointerEvent, Graphics, Sprite } from 'pixi.js'
import { SCENE_WIDTH, SCENE_HEIGHT, computeDesks } from './layout'
import { DeskActor, AgentActor } from './characters'
import type { AgentRecord } from './characters'
import { MissionRunner } from './missions'
import { resolveSceneTheme } from './theme'
import { loadOfficeTextures, getOfficeBackgroundTexture } from './assets'
import type { OfficeAction } from './types'

const AUTO_WORKFLOW_IDLE_SEC = 8

export interface OfficeAgentProfile {
  name: string
  color: number
  online: boolean
  busy: boolean
}

export interface OfficeSceneStrings {
  visitFallback: (hostName: string) => string
  ambientMessage: (visitorName: string, hostName: string) => string
}

export class OfficeSceneImpl {
  private app: Application | null = null
  private world: Container | null = null
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

    const app = new Application()
    await app.init({
      background: resolveSceneTheme().floor,
      antialias: true,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
      resizeTo: mount,
    })
    this.app = app
    mount.appendChild(app.canvas)
    app.canvas.style.display = 'block'

    this.onAgentClick = onAgentClick || null

    await loadOfficeTextures()

    const world = new Container()
    this.world = world
    app.stage.addChild(world)

    this.drawFloor()
    this.fitStage(mount)

    this.resizeObserver = new ResizeObserver(() => this.fitStage(mount))
    this.resizeObserver.observe(mount)

    app.ticker.add((ticker) => this.onTick(Math.min(ticker.deltaTime / 60, 0.05)))
    return true
  }

  private drawFloor(): void {
    const theme = resolveSceneTheme()
    const world = this.world!

    const bgTexture = getOfficeBackgroundTexture()
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

  /** 固定尺寸场景缩放到挂载点大小并居中（fitStage 的移植）。 */
  private fitStage(mount: HTMLElement): void {
    if (!this.app || !this.world) return
    const w = mount.clientWidth || SCENE_WIDTH
    const h = mount.clientHeight || SCENE_HEIGHT
    const scale = Math.min(w / SCENE_WIDTH, h / SCENE_HEIGHT)
    this.world.scale.set(scale)
    this.world.position.set((w - SCENE_WIDTH * scale) / 2, (h - SCENE_HEIGHT * scale) / 2)
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

    profiles.forEach((p, index) => {
      seen.add(p.name)
      const desk = desks[index]
      if (!desk) return
      let agent = this.agents.get(p.name)
      if (!agent) {
        agent = this.createAgent(p, desk)
        this.agents.set(p.name, agent)
      }
      agent.desk = desk
      agent.deskActor.desk = desk
      agent.deskActor.position.set(desk.x, desk.y)
      const base: AgentRecord['baseState'] = p.busy ? 'working' : p.online ? 'online' : 'offline'
      agent.baseState = base
      agent.deskActor.setStatus(base)
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
    const deskActor = new DeskActor(desk, profile.name)
    deskActor.position.set(desk.x, desk.y)
    deskActor.zIndex = desk.seatY - 20
    world.addChild(deskActor)

    const actor = new AgentActor(profile.name, profile.color)
    actor.position.set(desk.seatX, desk.seatY)
    actor.on('pointertap', (event: FederatedPointerEvent) => {
      this.onAgentClick?.({
        name: profile.name,
        clientX: event.clientX,
        clientY: event.clientY,
      })
    })
    world.addChild(actor)

    const base: AgentRecord['baseState'] = profile.busy ? 'working' : profile.online ? 'online' : 'offline'
    const agent: AgentRecord = {
      name: profile.name,
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
      mission: undefined,
    }
    actor.setState(base)
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
    this.app?.destroy(true, { children: true })
    this.app = null
    this.world = null
    this.agents.clear()
  }

  private onTick(dt: number): void {
    if (!this.world) return

    this.runner.tick(dt)

    for (const agent of this.agents.values()) {
      agent.actor.update(dt, this.reducedMotion)
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
