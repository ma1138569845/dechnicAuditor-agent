import type { CronJob } from '@/types/hermes'

import {
  isActiveKanbanBusyStatus,
  isKanbanTaskBusyForProfile,
  jobMentionsProfile,
  type OfficeKanbanBusyTask
} from './status'

export type OfficeWorkKind = 'kanban' | 'cron'

export interface OfficeCurrentWork {
  kind: OfficeWorkKind
  /** Short title for desk labels. */
  summary: string
  /** Full title when available. */
  detail: string
}

const KANBAN_PRIORITY = ['running', 'ready', 'blocked', 'review', 'todo', 'scheduled', 'triage'] as const

function truncate(text: string, max = 22): string {
  const t = text.trim().replace(/\s+/g, ' ')
  if (t.length <= max) return t
  return `${t.slice(0, Math.max(1, max - 1))}…`
}

/** Pick the most relevant open work item for a profile (kanban preferred). */
export function resolveCurrentWork(
  profileName: string,
  jobs: CronJob[],
  kanbanTasks: ReadonlyArray<OfficeKanbanBusyTask> = []
): OfficeCurrentWork | null {
  const assigned = kanbanTasks.filter(task => isKanbanTaskBusyForProfile(task, profileName))
  if (assigned.length > 0) {
    const ranked = [...assigned].sort((a, b) => {
      const ai = KANBAN_PRIORITY.indexOf(a.status as (typeof KANBAN_PRIORITY)[number])
      const bi = KANBAN_PRIORITY.indexOf(b.status as (typeof KANBAN_PRIORITY)[number])
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
    })
    const top = ranked[0]
    const detail = String(top.title || top.id).trim() || top.id
    return { kind: 'kanban', summary: truncate(detail), detail }
  }

  const cron = jobs.find(job => job.enabled && jobMentionsProfile(job, profileName))
  if (cron) {
    const detail = String(cron.name || cron.id || '').trim() || 'cron'
    return { kind: 'cron', summary: truncate(detail), detail }
  }

  // Defensive: busy flag might come from a status we didn't list.
  const anyBusy = kanbanTasks.find(
    task =>
      (task.assignee ?? '').trim().toLowerCase() === profileName.trim().toLowerCase() &&
      isActiveKanbanBusyStatus(task.status)
  )
  if (anyBusy) {
    const detail = String(anyBusy.title || anyBusy.id).trim() || anyBusy.id
    return { kind: 'kanban', summary: truncate(detail), detail }
  }

  return null
}
