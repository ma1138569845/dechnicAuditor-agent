import { describe, expect, it } from 'vitest'

import type { CronJob } from '@/types/hermes'

import {
  computeOfficeStats,
  isProfileBusy,
  isProfileOnline,
  jobMentionsProfile,
  resolveOfficeBaseState
} from './status'

function job(overrides: Partial<CronJob>): CronJob {
  return {
    id: 'j-1',
    enabled: true,
    ...overrides
  } as CronJob
}

describe('isProfileOnline', () => {
  it('is true only when gateway_running is exactly true (secondary signal)', () => {
    expect(isProfileOnline({ gateway_running: true })).toBe(true)
    expect(isProfileOnline({ gateway_running: false })).toBe(false)
    expect(isProfileOnline({})).toBe(false)
    expect(isProfileOnline({ gateway_running: null })).toBe(false)
  })
})

describe('busy / job mention heuristic', () => {
  it('matches enabled jobs that mention the profile in name or prompt', () => {
    const jobs = [
      job({ name: '报告 alice', enabled: true }),
      job({ name: '其他', prompt: 'ping bob', enabled: true }),
      job({ name: '停用 alice', enabled: false })
    ]
    expect(isProfileBusy('alice', jobs)).toBe(true)
    expect(isProfileBusy('bob', jobs)).toBe(true)
    expect(isProfileBusy('carol', jobs)).toBe(false)
    expect(jobMentionsProfile(jobs[2], 'alice')).toBe(true)
  })

  it('also treats active assigned kanban tasks as busy', () => {
    expect(
      isProfileBusy('alice', [], [{ id: 't1', status: 'running', assignee: 'alice' }])
    ).toBe(true)
    expect(
      isProfileBusy('alice', [], [{ id: 't2', status: 'archived', assignee: 'alice' }])
    ).toBe(false)
    expect(
      isProfileBusy('alice', [], [{ id: 't3', status: 'ready', assignee: 'bob' }])
    ).toBe(false)
  })
})

describe('resolveOfficeBaseState', () => {
  it('is work-centric: busy → working, else online', () => {
    expect(resolveOfficeBaseState(true)).toBe('working')
    expect(resolveOfficeBaseState(false)).toBe('online')
  })
})

describe('computeOfficeStats', () => {
  it('counts idle/busy agents and open/done-today cron jobs', () => {
    const now = new Date('2026-08-28T12:00:00').getTime()
    const startOfDay = new Date(now).setHours(0, 0, 0, 0)
    const stats = computeOfficeStats(
      [
        { online: true, busy: true },
        { online: true, busy: false },
        { online: false, busy: false }
      ],
      [
        job({ enabled: true, last_run_at: String(startOfDay + 1) }),
        job({ enabled: true, last_run_at: String(startOfDay - 1) }),
        job({ enabled: false, last_run_at: String(startOfDay + 1) })
      ],
      now
    )
    // online field = idle count (2 not busy), regardless of gateway flags
    expect(stats).toEqual({ online: 2, busy: 1, openTasks: 2, doneToday: 1 })
  })
})
