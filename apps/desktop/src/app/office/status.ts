import type { CronJob } from '@/types/hermes'

/**
 * Office agent status contract (work-centric).
 *
 * Scene baseState: busy → working, else → online (idle at desk).
 * Messaging `gateway_running` is stored on the profile as `online` for a
 * secondary “gateway off” hint — it no longer drives the main presence.
 *
 * busy: enabled cron whose name/prompt mentions the profile, OR an active
 * Kanban task assigned to the profile.
 */

export type OfficeBaseState = 'working' | 'online'

/** Kanban statuses that count as "in progress" for office busy. */
export const OFFICE_BUSY_KANBAN_STATUSES = new Set([
  'triage',
  'todo',
  'scheduled',
  'ready',
  'running',
  'blocked',
  'review'
])

export interface OfficeKanbanBusyTask {
  id: string
  status: string
  assignee?: null | string
  title?: null | string
}

/** Secondary signal only — messaging gateway process for this profile. */
export function isProfileOnline(profile: { gateway_running?: boolean | null }): boolean {
  return profile.gateway_running === true
}

export function jobMentionsProfile(job: CronJob, profileName: string): boolean {
  const hay = `${job.name ?? ''} ${job.prompt ?? ''}`.toLowerCase()
  return hay.includes(profileName.toLowerCase())
}

export function isActiveKanbanBusyStatus(status: string): boolean {
  return OFFICE_BUSY_KANBAN_STATUSES.has(status)
}

export function isKanbanTaskBusyForProfile(task: OfficeKanbanBusyTask, profileName: string): boolean {
  const assignee = (task.assignee ?? '').trim().toLowerCase()
  if (!assignee || assignee !== profileName.trim().toLowerCase()) return false
  return isActiveKanbanBusyStatus(task.status)
}

export function isProfileBusy(
  profileName: string,
  jobs: CronJob[],
  kanbanTasks: ReadonlyArray<OfficeKanbanBusyTask> = []
): boolean {
  if (jobs.some(job => job.enabled && jobMentionsProfile(job, profileName))) return true
  return kanbanTasks.some(task => isKanbanTaskBusyForProfile(task, profileName))
}

/** Work-centric scene base: busy → working, otherwise idle-online. */
export function resolveOfficeBaseState(busy: boolean): OfficeBaseState {
  return busy ? 'working' : 'online'
}

export function computeOfficeStats(
  profiles: ReadonlyArray<{ online: boolean; busy: boolean }>,
  jobs: CronJob[],
  now = Date.now(),
  kanbanTasks: ReadonlyArray<OfficeKanbanBusyTask> = []
): { online: number; busy: number; openTasks: number; doneToday: number } {
  const startOfDay = new Date(now).setHours(0, 0, 0, 0)
  const openCron = jobs.filter(job => job.enabled).length
  const openKanban = kanbanTasks.filter(task => isActiveKanbanBusyStatus(task.status)).length
  return {
    // `online` field = idle count (not gateway-up). Kept for wire compatibility.
    online: profiles.filter(p => !p.busy).length,
    busy: profiles.filter(p => p.busy).length,
    openTasks: openCron + openKanban,
    doneToday: jobs.filter(job => job.enabled && Number(job.last_run_at ?? 0) >= startOfDay).length
  }
}
