import { atom } from 'nanostores'

import { getCronJobs } from '@/api/cron'
import { pluginRest } from '@/api/plugins'
import { translateNow } from '@/i18n'
import { $profiles, profileLabel, refreshProfiles } from '@/store/profile'
import type { CronJob } from '@/types/hermes'

import { pushOfficeActivity, recordOfficeAction, resetOfficeActivity } from './activity'
import type { OfficeAgentProfile } from './engine/engine'
import { agentColor } from './engine/theme'
import type { OfficeAction } from './engine/types'
import { resolveCurrentWork } from './current-work'
import {
  computeOfficeStats,
  isActiveKanbanBusyStatus,
  isProfileBusy,
  isProfileOnline,
  jobMentionsProfile,
  type OfficeKanbanBusyTask
} from './status'

export type LedgerFilter = 'all' | 'open' | 'done'

export const $ledgerFilter = atom<LedgerFilter>('all')
export const $activeAgent = atom<string | null>(null)
export const $cronJobs = atom<CronJob[]>([])
export const $kanbanTasks = atom<OfficeKanbanBusyTask[]>([])
export const $officeProfiles = atom<OfficeAgentProfile[]>([])
export const $stats = atom<{ online: number; busy: number; openTasks: number; doneToday: number }>({
  online: 0,
  busy: 0,
  openTasks: 0,
  doneToday: 0
})

interface KanbanBoardResponse {
  columns: Array<{ tasks: OfficeKanbanBusyTask[] }>
}

// 场景桥：页面挂载 scene 后注入（同进程直调，不走 HTTP 动作队列）。
let enqueueAction: ((action: OfficeAction) => boolean) | null = null
let playEmoteFn: ((name: string, animation: string) => boolean) | null = null
let refreshTimer: ReturnType<typeof setInterval> | null = null
let visibilityHandler: (() => void) | null = null
let prevJobs = new Map<string, CronJob>()
let prevKanbanIds = new Set<string>()
/** True after the first successful kanban fetch (even if the board is empty). */
let kanbanHydrated = false

const REFRESH_MS = 15_000

export function attachSceneEnqueue(fn: (action: OfficeAction) => boolean): void {
  enqueueAction = fn
}

export function attachScenePlayEmote(fn: (name: string, animation: string) => boolean): void {
  playEmoteFn = fn
}

export function detachSceneEnqueue(): void {
  enqueueAction = null
  playEmoteFn = null
}

function emitAction(action: OfficeAction): boolean {
  if (!enqueueAction) return false
  const ok = enqueueAction(action)
  if (ok) recordOfficeAction(action)
  return ok
}

/** Scene-only state override (transient until the next profile sync). */
export function dispatchSetState(
  profile: string,
  state: 'working' | 'online' | 'offline' | 'thinking',
  task?: string
): boolean {
  return emitAction({ type: 'set_state', profile, state, task })
}

/** Send visitor to host's desk (walk → talk → return). */
export function dispatchDeskVisit(visitor: string, host: string, message?: string): boolean {
  if (!visitor || !host || visitor === host) return false
  return emitAction({ type: 'desk_visit', visitor, host, message })
}

export function dispatchCelebrate(target: string): boolean {
  if (!target) return false
  return emitAction({ type: 'celebrate', target })
}

export function dispatchBroadcast(message: string): boolean {
  const text = message.trim()
  if (!text) return false
  return emitAction({ type: 'broadcast', message: text })
}

/** Trigger a short chibi emote on the named agent (not an OfficeAction queue item). */
export function dispatchPlayEmote(profile: string, animation: string): boolean {
  if (!profile || !animation || !playEmoteFn) return false
  const ok = playEmoteFn(profile, animation)
  if (ok) {
    pushOfficeActivity('emote', translateNow('office.activity.emote', profile))
  }
  return ok
}

/** Prefer the longest profile name mentioned in a job title/prompt. */
export function resolveHostProfile(jobText: string, profileNames: string[]): string | null {
  const hay = jobText.toLowerCase()
  const hits = profileNames.filter(name => hay.includes(name.toLowerCase()))
  if (hits.length === 0) return null
  return hits.sort((a, b) => b.length - a.length)[0]
}

function castProfileNames(): string[] {
  // Desk visits can involve any rostered profile — gateway is not required.
  return $profiles.get().map(p => p.name)
}

function jobCastText(job: CronJob): string {
  return `${job.name ?? ''} ${job.prompt ?? ''}`
}

/**
 * Diff cron snapshots into scene actions:
 * - new enabled job naming a host → dispatcher visits with localized title
 * - last_run_at advanced → assignee celebrates
 * First load (empty prev) intentionally fires nothing.
 */
function detectBoardEvents(prev: Map<string, CronJob>, next: CronJob[]): void {
  if (prev.size === 0 || !enqueueAction) return
  const cast = castProfileNames()
  if (cast.length === 0) return

  for (const job of next) {
    const before = prev.get(job.id)
    if (!before) {
      if (!job.enabled || !job.name) continue
      const host = resolveHostProfile(jobCastText(job), cast)
      if (!host) continue
      const visitor = cast.find(name => name !== host) ?? cast[0]
      if (visitor === host) continue
      const title = String(job.name).slice(0, 60)
      emitAction({
        type: 'desk_visit',
        visitor,
        host,
        message: `${translateNow('office.newTaskPrefix')}: ${title}`
      })
      continue
    }

    const prevRun = Number(before.last_run_at ?? 0)
    const nextRun = Number(job.last_run_at ?? 0)
    if (nextRun <= prevRun) continue
    const host = resolveHostProfile(jobCastText(job), cast)
    if (host) emitAction({ type: 'celebrate', target: host })
  }
}

function flattenKanbanBoard(board: KanbanBoardResponse | null | undefined): OfficeKanbanBusyTask[] {
  if (!board?.columns) return []
  return board.columns.flatMap(column => column.tasks ?? [])
}

/**
 * New active Kanban cards assigned to a host → another online agent visits.
 * First load (empty prev) intentionally fires nothing.
 */
function detectKanbanEvents(prevIds: Set<string>, next: OfficeKanbanBusyTask[]): void {
  // Use hydrated flag — an empty first board must still count as a baseline,
  // otherwise a later first card never triggers narrative.
  if (!kanbanHydrated || !enqueueAction) return
  const cast = castProfileNames()
  if (cast.length === 0) return

  for (const task of next) {
    if (prevIds.has(task.id)) continue
    if (!isActiveKanbanBusyStatus(task.status)) continue
    const host = (task.assignee ?? '').trim()
    if (!host || !cast.includes(host)) continue
    const visitor = cast.find(name => name !== host) ?? cast[0]
    if (visitor === host) continue
    const title = String(task.title || task.id).slice(0, 60)
    emitAction({
      type: 'desk_visit',
      visitor,
      host,
      message: `${translateNow('office.newTaskPrefix')}: ${title}`
    })
  }
}

function rebuildOfficeProfiles(
  jobs: CronJob[],
  kanbanTasks: OfficeKanbanBusyTask[]
): OfficeAgentProfile[] {
  return $profiles.get().map(profile => {
    const name = profile.name
    const busy = isProfileBusy(name, jobs, kanbanTasks)
    const work = busy ? resolveCurrentWork(name, jobs, kanbanTasks) : null
    return {
      name,
      label: profileLabel(profile),
      color: agentColor(name),
      online: isProfileOnline(profile),
      busy,
      currentWork: work?.summary ?? null
    } satisfies OfficeAgentProfile
  })
}

/** 单次刷新（导出供测试手动触发，生产由 startOfficeStore 的 interval 驱动）。 */
export async function refreshOfficeStore(options?: { manual?: boolean }): Promise<void> {
  // Profiles carry gateway_running — refresh so online status stays live.
  try {
    await refreshProfiles()
  } catch {
    // Keep the last successful $profiles snapshot.
  }

  let jobs = $cronJobs.get()
  try {
    jobs = await getCronJobs()
    detectBoardEvents(prevJobs, jobs)
    prevJobs = new Map(jobs.map(job => [job.id, job]))
    $cronJobs.set(jobs)
  } catch {
    // 拉取失败保持现有 cron 数据；仍用当前 jobs 重算 busy/online。
  }

  let kanbanTasks = $kanbanTasks.get()
  try {
    const board = await pluginRest<KanbanBoardResponse>('kanban', '/board?include_archived=true')
    kanbanTasks = flattenKanbanBoard(board)
    detectKanbanEvents(prevKanbanIds, kanbanTasks)
    prevKanbanIds = new Set(kanbanTasks.map(task => task.id))
    kanbanHydrated = true
    $kanbanTasks.set(kanbanTasks)
  } catch {
    // Kanban plugin unavailable — keep last snapshot (or empty).
  }

  const officeProfiles = rebuildOfficeProfiles(jobs, kanbanTasks)
  $officeProfiles.set(officeProfiles)
  $stats.set(computeOfficeStats(officeProfiles, jobs, Date.now(), kanbanTasks))
  if (options?.manual) {
    pushOfficeActivity('refresh', translateNow('office.activity.refreshed'))
  }
}

function isDocumentVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden'
}

/** 测试辅助：清空模块级状态（prev 快照/timer/动作桥）。 */
export function resetOfficeStore(): void {
  stopOfficeStore()
  detachSceneEnqueue()
  resetOfficeActivity()
  prevJobs = new Map()
  prevKanbanIds = new Set()
  kanbanHydrated = false
  $cronJobs.set([])
  $kanbanTasks.set([])
  $officeProfiles.set([])
  $stats.set({ online: 0, busy: 0, openTasks: 0, doneToday: 0 })
}

/** 进入办公室页：立即拉一次 + 15s 刷新（标签页隐藏时暂停）。 */
export function startOfficeStore(): void {
  if (refreshTimer) return
  void refreshOfficeStore()
  refreshTimer = setInterval(() => {
    if (!isDocumentVisible()) return
    void refreshOfficeStore()
  }, REFRESH_MS)

  if (typeof document !== 'undefined' && !visibilityHandler) {
    visibilityHandler = () => {
      if (isDocumentVisible()) void refreshOfficeStore()
    }
    document.addEventListener('visibilitychange', visibilityHandler)
  }
}

/** 离开办公室页：停止刷新（引擎由 scene 组件卸载销毁）。 */
export function stopOfficeStore(): void {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (visibilityHandler && typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', visibilityHandler)
    visibilityHandler = null
  }
}

// Re-export for callers/tests that previously imported the heuristic here.
export { jobMentionsProfile }
