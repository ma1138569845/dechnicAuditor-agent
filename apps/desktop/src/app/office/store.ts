import { atom } from 'nanostores'

import { getCronJobs } from '@/api/cron'
import { $profiles } from '@/store/profile'
import type { CronJob } from '@/types/hermes'

import type { OfficeAgentProfile } from './engine/engine'
import { agentColor } from './engine/theme'
import type { OfficeAction } from './engine/types'

export type LedgerFilter = 'all' | 'open' | 'done'

export const $ledgerFilter = atom<LedgerFilter>('all')
export const $activeAgent = atom<string | null>(null)
export const $cronJobs = atom<CronJob[]>([])
export const $officeProfiles = atom<OfficeAgentProfile[]>([])
export const $stats = atom<{ online: number; busy: number; openTasks: number; doneToday: number }>({
  online: 0,
  busy: 0,
  openTasks: 0,
  doneToday: 0
})

// 场景 enqueue 桥：页面挂载 scene 后注入（同进程直调，不走 HTTP 动作队列）。
let enqueueAction: ((action: OfficeAction) => boolean) | null = null
let refreshTimer: ReturnType<typeof setInterval> | null = null
let prevJobs = new Map<string, CronJob>()

export function attachSceneEnqueue(fn: (action: OfficeAction) => boolean): void {
  enqueueAction = fn
}

export function detachSceneEnqueue(): void {
  enqueueAction = null
}

/** 对比两次 cron 快照，把变化翻译成场景动作（新增任务 → desk_visit）。 */
function detectBoardEvents(prev: Map<string, CronJob>, next: CronJob[]): void {
  if (prev.size === 0 || !enqueueAction) return
  const onlineNames = $profiles.get().map(p => p.name)
  for (const job of next) {
    if (prev.has(job.id) || !job.enabled || !job.name) continue
    const host = job.name.trim().split(' ')[0]
    if (!host || onlineNames.length === 0) continue
    const visitor = onlineNames[0]
    if (visitor !== host) {
      enqueueAction({ type: 'desk_visit', visitor, host, message: `${job.name}` })
    }
  }
}

/** 单次刷新（导出供测试手动触发，生产由 startOfficeStore 的 interval 驱动）。 */
export async function refreshOfficeStore(): Promise<void> {
  let jobs: CronJob[] = []
  try {
    jobs = await getCronJobs()
    detectBoardEvents(prevJobs, jobs)
    prevJobs = new Map(jobs.map(job => [job.id, job]))
    $cronJobs.set(jobs)
  } catch {
    // 拉取失败保持现有数据（页面加载期间静默）。
  }

  // 状态近似（MVP）：online=已配置 profile；busy=该 profile 有启用中的 cron 任务。
  const profiles = $profiles.get()
  const officeProfiles = profiles.map(profile => {
    const name = profile.name
    return {
      name,
      color: agentColor(name),
      online: true,
      busy: jobs.some(job => job.enabled && (job.name ?? '').includes(name))
    } satisfies OfficeAgentProfile
  })
  $officeProfiles.set(officeProfiles)

  const startOfDay = new Date().setHours(0, 0, 0, 0)
  $stats.set({
    online: officeProfiles.filter(p => p.online).length,
    busy: officeProfiles.filter(p => p.busy).length,
    openTasks: jobs.filter(job => job.enabled).length,
    doneToday: jobs.filter(job => job.enabled && Number(job.last_run_at ?? 0) >= startOfDay).length
  })
}

/** 测试辅助：清空模块级状态（prev 快照/timer/动作桥）。 */
export function resetOfficeStore(): void {
  stopOfficeStore()
  detachSceneEnqueue()
  prevJobs = new Map()
  $cronJobs.set([])
  $officeProfiles.set([])
  $stats.set({ online: 0, busy: 0, openTasks: 0, doneToday: 0 })
}

/** 进入办公室页：立即拉一次 + 15s 刷新。 */
export function startOfficeStore(): void {
  if (refreshTimer) return
  void refreshOfficeStore()
  refreshTimer = setInterval(() => void refreshOfficeStore(), 15_000)
}

/** 离开办公室页：停止刷新（引擎由 scene 组件卸载销毁）。 */
export function stopOfficeStore(): void {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}
