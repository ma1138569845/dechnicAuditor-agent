/**
 * 工位拜访任务状态机 + 移动 + 串行动作队列。
 * 移植自 dechnic-auditor-agent-main（源自 ai-office-react-main）：
 *  - src/scene/simulation/deskVisit.ts  （goto → talk → return FSM、交谈对象）
 *  - src/scene/systems/MovementSystem.ts（途经点行走、到达阈值）
 *  - src/services/officeActionDispatcher.ts（串行队列、busy 门控）
 * 简化：agent 以 profile 名为键；路径为 L 形（layout.planPath）。
 */
import type { OfficeAction } from './types'
import { planPath, visitSpotFor } from './layout'
import type { AgentRecord } from './characters'

const WALK_SPEED = 150
const ARRIVE_THRESHOLD = 6
const DEFAULT_TALK_SEC = 3.5

function facingToward(fromX: number, toX: number): number {
  return toX >= fromX ? 1 : -1
}

export interface MissionStrings {
  visitFallback: (hostName: string) => string
}

export class MissionRunner {
  private readonly agents: Map<string, AgentRecord>
  private readonly strings: MissionStrings
  private readonly queue: OfficeAction[] = []
  reducedMotion = false

  constructor(agents: Map<string, AgentRecord>, strings: MissionStrings) {
    this.agents = agents
    this.strings = strings
  }

  get busy(): boolean {
    for (const a of this.agents.values()) if (a.mission) return true
    return false
  }

  get pending(): number {
    return this.queue.length
  }

  /** 校验 + 入队一个外部/场景动作。无效动作直接丢弃。 */
  enqueue(action: OfficeAction): boolean {
    const normalized = this.normalize(action)
    if (!normalized) {
      console.warn('[OfficeScene] invalid action, dropped', action)
      return false
    }
    this.queue.push(normalized)
    return true
  }

  private normalize(action: OfficeAction): OfficeAction | null {
    const has = (name: string) => this.agents.has(name)
    switch (action.type) {
      case 'desk_visit': {
        const { visitor, host, message } = action
        if (!has(visitor) || !has(host) || visitor === host) return null
        if (this.agents.get(visitor)?.baseState === 'offline') return null
        return { type: action.type, visitor, host, message: String(message || '') }
      }
      case 'desk_visit_tour': {
        const hosts = [...new Set(action.hosts || [])].filter((h) => has(h) && h !== action.visitor)
        if (!has(action.visitor) || hosts.length === 0) return null
        if (this.agents.get(action.visitor)?.baseState === 'offline') return null
        return { type: action.type, visitor: action.visitor, hosts, message: String(action.message || '') }
      }
      case 'set_state': {
        const allowed = ['working', 'online', 'offline', 'thinking']
        if (!has(action.profile) || !allowed.includes(action.state)) return null
        return { type: action.type, profile: action.profile, state: action.state, task: action.task ? String(action.task) : '' }
      }
      case 'broadcast':
        return action.message ? { type: action.type, message: String(action.message) } : null
      case 'celebrate':
        return has(action.target) ? { type: action.type, target: action.target } : null
      default:
        return null
    }
  }

  /** 无任务运行时启动下一条排队动作。 */
  private drain(): void {
    if (this.busy || this.queue.length === 0) return
    const action = this.queue.shift()
    if (action) this.execute(action)
  }

  private execute(action: OfficeAction): void {
    switch (action.type) {
      case 'desk_visit':
        this.startVisit(action.visitor, [{ host: action.host, message: action.message }])
        break
      case 'desk_visit_tour':
        this.startVisit(
          action.visitor,
          action.hosts.map((h) => ({ host: h, message: action.message })),
        )
        break
      case 'set_state': {
        const agent = this.agents.get(action.profile)
        if (!agent) return
        agent.baseState = action.state === 'thinking' ? 'thinking' : action.state
        if (action.task) agent.baseTask = action.task
        if (!agent.mission) this.applyActorState(agent)
        break
      }
      case 'broadcast':
        for (const agent of this.agents.values()) {
          if (agent.baseState !== 'offline') agent.actor.showBubble(action.message, 4)
        }
        break
      case 'celebrate': {
        const agent = this.agents.get(action.target)
        if (agent && !agent.mission && agent.baseState !== 'offline') {
          agent.actor.celebrate()
          agent.actor.showBubble('✓', 1.6)
        }
        break
      }
    }
  }

  /** 启动一个 goto→talk→return 任务，经过给定 stops。 */
  private startVisit(visitorName: string, stops: { host: string; message?: string }[]): void {
    const visitor = this.agents.get(visitorName)
    if (!visitor || stops.length === 0 || visitor.mission) return

    const [first, ...rest] = stops
    visitor.mission = {
      phase: 'goto',
      hostName: first.host,
      message: first.message || this.strings.visitFallback(first.host),
      talkDuration: DEFAULT_TALK_SEC,
      queue: rest.map((s) => ({ host: s.host, message: s.message || this.strings.visitFallback(s.host) })),
    }
    this.assignWalkToHost(visitor, first.host)
  }

  private assignWalkToHost(visitor: AgentRecord, hostName: string): void {
    const host = this.agents.get(hostName)
    if (!host) return
    const spot = visitSpotFor(host.desk.seatX, host.desk.seatY, visitor.x)
    this.assignWalk(visitor, planPath(visitor.x, visitor.y, spot.x, spot.y))
  }

  private assignWalk(agent: AgentRecord, path: { x: number; y: number }[]): void {
    if (this.reducedMotion && path.length > 0) {
      const last = path[path.length - 1]
      agent.x = last.x
      agent.y = last.y
      agent.walkPath = undefined
      agent.targetX = undefined
      agent.actor.position.set(agent.x, agent.y)
      return
    }
    if (path.length === 0) return
    agent.walkPath = path
    agent.walkPathIndex = 0
    agent.targetX = path[0].x
    agent.targetY = path[0].y
    agent.state = 'walking'
    agent.actor.setState('walking')
    agent.actor.setFacing(facingToward(agent.x, agent.targetX))
  }

  /** 移动 — MovementSystem.update 的移植。 */
  private moveAgents(dt: number): void {
    for (const agent of this.agents.values()) {
      if (agent.state !== 'walking' || agent.targetX == null || agent.targetY == null) continue

      const dx = agent.targetX - agent.x
      const dy = agent.targetY - agent.y
      const dist = Math.hypot(dx, dy)

      if (dist < ARRIVE_THRESHOLD) {
        agent.x = agent.targetX
        agent.y = agent.targetY
        const hasMore = agent.walkPath && agent.walkPathIndex != null && agent.walkPathIndex < agent.walkPath.length - 1
        if (hasMore) {
          agent.walkPathIndex = (agent.walkPathIndex ?? 0) + 1
          const next = agent.walkPath![agent.walkPathIndex!]
          agent.targetX = next.x
          agent.targetY = next.y
          agent.actor.setFacing(facingToward(agent.x, next.x))
        } else {
          agent.targetX = undefined
          agent.targetY = undefined
          agent.walkPath = undefined
          agent.state = 'idle' // 已就位——任务 FSM 下帧重新标记
        }
        agent.actor.position.set(agent.x, agent.y)
        continue
      }

      const step = Math.min(WALK_SPEED * dt, dist)
      agent.x += (dx / dist) * step
      agent.y += (dy / dist) * step
      agent.actor.setFacing(facingToward(agent.x, agent.targetX))
      agent.actor.position.set(agent.x, agent.y)
    }
  }

  /** 任务 FSM — processDeskVisitMissions 的移植。 */
  private processMissions(dt: number): void {
    for (const agent of this.agents.values()) {
      const m = agent.mission
      if (!m) continue

      if (m.phase === 'goto') {
        if (agent.state === 'walking' || agent.targetX != null) continue
        const host = this.agents.get(m.hostName)
        agent.actor.setFacing(host ? facingToward(agent.x, host.x) : 1)
        agent.actor.showBubble(m.message, m.talkDuration)
        agent.state = 'talking'
        agent.actor.setState('talking')
        agent.mission = { ...m, phase: 'talk', talkRemaining: m.talkDuration }
        continue
      }

      if (m.phase === 'talk') {
        const left = (m.talkRemaining ?? m.talkDuration) - dt
        if (left > 0) {
          agent.mission = { ...m, talkRemaining: left }
          continue
        }
        agent.actor.hideBubble()
        if (m.queue.length > 0) {
          const [next, ...rest] = m.queue
          agent.mission = { ...m, phase: 'goto', hostName: next.host, message: next.message, queue: rest, talkRemaining: undefined }
          this.assignWalkToHost(agent, next.host)
        } else {
          const home = planPath(agent.x, agent.y, agent.desk.seatX, agent.desk.seatY)
          agent.mission = { ...m, phase: 'return' }
          this.assignWalk(agent, home)
        }
        continue
      }

      if (m.phase === 'return') {
        if (agent.state === 'walking' || agent.targetX != null) continue
        agent.mission = undefined
        agent.state = agent.baseState
        this.applyActorState(agent)
      }
    }

    this.syncTalkPartners()
  }

  /** 被交谈的 host 面向访客并播放交谈动画。 */
  private syncTalkPartners(): void {
    const hostToVisitor = new Map<string, AgentRecord>()
    for (const a of this.agents.values()) {
      if (a.mission?.phase === 'talk') hostToVisitor.set(a.mission.hostName, a)
    }
    for (const agent of this.agents.values()) {
      if (agent.mission) continue // 任务 FSM 拥有 actor 的状态
      const visitor = hostToVisitor.get(agent.name)
      if (visitor) {
        agent.actor.setState('talking')
        agent.actor.setFacing(facingToward(agent.x, visitor.x))
      } else if (agent.state !== 'walking' && agent.state !== agent.baseState) {
        // 无任务、无人拜访 — 回归基础状态。
        agent.state = agent.baseState
        this.applyActorState(agent)
      }
    }
  }

  private applyActorState(agent: AgentRecord): void {
    agent.actor.setState(agent.baseState)
    if (agent.baseState === 'thinking') {
      agent.actor.showBubble('…', 6)
    }
  }

  /** 场景每帧 tick。 */
  tick(dt: number): void {
    this.drain()
    this.moveAgents(dt)
    this.processMissions(dt)
  }
}
