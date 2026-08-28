import { atom } from 'nanostores'

import { translateNow } from '@/i18n'

import type { OfficeAction } from './engine/types'

export interface OfficeActivityItem {
  id: string
  at: number
  kind: OfficeAction['type'] | 'refresh' | 'emote'
  summary: string
}

const MAX_ACTIVITY = 20

export const $officeActivity = atom<OfficeActivityItem[]>([])

export function resetOfficeActivity(): void {
  $officeActivity.set([])
}

export function summarizeOfficeAction(action: OfficeAction): string {
  switch (action.type) {
    case 'desk_visit':
      return translateNow('office.activity.visit', action.visitor, action.host)
    case 'desk_visit_tour':
      return translateNow('office.activity.tour', action.visitor, String(action.hosts.length))
    case 'set_state':
      return translateNow('office.activity.setState', action.profile, action.state)
    case 'celebrate':
      return translateNow('office.activity.celebrate', action.target)
    case 'broadcast':
      return translateNow('office.activity.broadcast', action.message.slice(0, 40))
    default:
      return translateNow('office.activity.unknown')
  }
}

export function pushOfficeActivity(
  kind: OfficeActivityItem['kind'],
  summary: string,
  at = Date.now()
): void {
  const item: OfficeActivityItem = {
    id: `${at}-${Math.random().toString(36).slice(2, 8)}`,
    at,
    kind,
    summary
  }
  $officeActivity.set([item, ...$officeActivity.get()].slice(0, MAX_ACTIVITY))
}

export function recordOfficeAction(action: OfficeAction): void {
  pushOfficeActivity(action.type, summarizeOfficeAction(action))
}
