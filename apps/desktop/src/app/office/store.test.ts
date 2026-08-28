import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getCronJobs } from '@/api/cron'
import type { CronJob } from '@/types/hermes'

import {
  attachSceneEnqueue,
  refreshOfficeStore,
  resetOfficeStore,
  $cronJobs,
  $officeProfiles,
  $stats
} from './store'

vi.mock('@/api/cron', () => ({ getCronJobs: vi.fn() }))
vi.mock('@/store/profile', () => ({
  $profiles: { get: () => [{ name: 'alice' }, { name: 'bob' }] }
}))

function job(overrides: Partial<CronJob>): CronJob {
  return {
    id: 'j-' + Math.random().toString(36).slice(2, 8),
    enabled: true,
    ...overrides
  } as CronJob
}

beforeEach(() => {
  vi.clearAllMocks()
  resetOfficeStore()
})

describe('office store refresh', () => {
  it('fills profiles and stats from cron jobs', async () => {
    const now = Date.now()
    vi.mocked(getCronJobs).mockResolvedValue([
      job({ name: '报告 alice', enabled: true, last_run_at: String(now) }),
      job({ name: '已停用', enabled: false })
    ])

    await refreshOfficeStore()

    expect($stats.get()).toEqual({ online: 2, busy: 1, openTasks: 1, doneToday: 1 })
    expect($officeProfiles.get().find(p => p.name === 'alice')?.busy).toBe(true)
    expect($officeProfiles.get().find(p => p.name === 'bob')?.busy).toBe(false)
  })

  it('keeps prior data when the fetch fails', async () => {
    $cronJobs.set([job({ id: 'keep', name: 'keep', enabled: true })])
    vi.mocked(getCronJobs).mockRejectedValue(new Error('down'))

    await refreshOfficeStore()

    expect($cronJobs.get().some(j => j.id === 'keep')).toBe(true)
  })
})

describe('detectBoardEvents', () => {
  it('enqueues a desk_visit when a new job appears', async () => {
    const enqueue = vi.fn(() => true)
    attachSceneEnqueue(enqueue)

    const first = job({ id: 'existing', name: '任务一', enabled: true })
    const fresh = job({ id: 'new-job', name: '新任务 x', enabled: true })
    vi.mocked(getCronJobs)
      .mockResolvedValueOnce([first])
      .mockResolvedValueOnce([first, fresh])

    await refreshOfficeStore()
    await refreshOfficeStore()

    expect(enqueue).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'desk_visit', host: '新任务', message: '新任务 x' })
    )
  })

  it('does not enqueue on first load (no previous snapshot)', async () => {
    const enqueue = vi.fn(() => true)
    attachSceneEnqueue(enqueue)
    vi.mocked(getCronJobs).mockResolvedValue([job({ name: '任务一', enabled: true })])

    await refreshOfficeStore()

    expect(enqueue).not.toHaveBeenCalled()
  })
})
