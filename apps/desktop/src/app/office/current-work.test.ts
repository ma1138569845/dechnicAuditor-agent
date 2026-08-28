import { describe, expect, it } from 'vitest'

import type { CronJob } from '@/types/hermes'

import { resolveCurrentWork } from './current-work'

function job(overrides: Partial<CronJob>): CronJob {
  return { id: 'j1', enabled: true, ...overrides } as CronJob
}

describe('resolveCurrentWork', () => {
  it('prefers running kanban over ready and over cron', () => {
    const work = resolveCurrentWork(
      'alice',
      [job({ name: 'cron alice', enabled: true })],
      [
        { id: 't1', title: 'Ready card', status: 'ready', assignee: 'alice' },
        { id: 't2', title: 'Running card for alice', status: 'running', assignee: 'alice' }
      ]
    )
    expect(work?.kind).toBe('kanban')
    expect(work?.detail).toBe('Running card for alice')
    expect(work?.summary.length).toBeLessThanOrEqual(22)
  })

  it('falls back to enabled cron that mentions the profile', () => {
    const work = resolveCurrentWork('bob', [job({ name: '每日 bob 巡检', enabled: true })], [])
    expect(work).toMatchObject({ kind: 'cron', detail: '每日 bob 巡检' })
  })

  it('returns null when idle', () => {
    expect(resolveCurrentWork('carol', [job({ name: 'alice only', enabled: true })], [])).toBeNull()
  })
})
