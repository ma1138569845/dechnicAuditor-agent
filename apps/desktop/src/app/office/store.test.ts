import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getCronJobs } from '@/api/cron'
import { pluginRest } from '@/api/plugins'
import type { CronJob, ProfileInfo } from '@/types/hermes'

import {
  attachSceneEnqueue,
  attachScenePlayEmote,
  dispatchCelebrate,
  dispatchDeskVisit,
  dispatchPlayEmote,
  dispatchSetState,
  refreshOfficeStore,
  resetOfficeStore,
  resolveHostProfile,
  $cronJobs,
  $officeProfiles,
  $stats
} from './store'

const profilesState = {
  list: [
    { name: 'alice', display_name: '爱丽丝', gateway_running: true },
    { name: 'bob', display_name: '', gateway_running: true }
  ] as Array<Pick<ProfileInfo, 'name' | 'display_name' | 'gateway_running'>>
}

const refreshProfiles = vi.fn(async () => profilesState.list)

vi.mock('@/api/cron', () => ({ getCronJobs: vi.fn() }))
vi.mock('@/api/plugins', () => ({ pluginRest: vi.fn() }))
vi.mock('@/i18n', () => ({
  translateNow: (key: string, ...args: unknown[]) => {
    if (key === 'office.newTaskPrefix') return '新任务'
    if (key === 'office.activity.visit') return `${args[0]} → ${args[1]}`
    if (key === 'office.activity.celebrate') return `${args[0]} ✓`
    if (key === 'office.activity.setState') return `${args[0]}:${args[1]}`
    if (key === 'office.activity.refreshed') return 'refreshed'
    if (key === 'office.activity.emote') return `${args[0]} emote`
    return key
  }
}))
vi.mock('@/store/profile', () => ({
  $profiles: {
    get: () => profilesState.list
  },
  profileLabel: (profile: { name: string; display_name?: string | null }) =>
    (profile.display_name ?? '').trim() || profile.name,
  refreshProfiles: () => refreshProfiles()
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
  profilesState.list = [
    { name: 'alice', display_name: '爱丽丝', gateway_running: true },
    { name: 'bob', display_name: '', gateway_running: true }
  ]
  refreshProfiles.mockResolvedValue(profilesState.list)
  vi.mocked(pluginRest).mockRejectedValue(new Error('kanban off'))
  vi.mocked(getCronJobs).mockResolvedValue([])
})

describe('resolveHostProfile', () => {
  it('picks the longest matching profile name', () => {
    expect(resolveHostProfile('报告 alice', ['alice', 'bob'])).toBe('alice')
    expect(resolveHostProfile('无匹配', ['alice', 'bob'])).toBeNull()
  })
})

describe('office store refresh', () => {
  it('fills profiles and stats from gateway + cron jobs', async () => {
    const now = Date.now()
    vi.mocked(getCronJobs).mockResolvedValue([
      job({ name: '报告 alice', enabled: true, last_run_at: String(now) }),
      job({ name: '已停用', enabled: false })
    ])

    await refreshOfficeStore()

    expect(refreshProfiles).toHaveBeenCalled()
    expect($stats.get()).toEqual({ online: 1, busy: 1, openTasks: 1, doneToday: 1 })
    expect($officeProfiles.get().find(p => p.name === 'alice')).toMatchObject({
      label: '爱丽丝',
      online: true,
      busy: true,
      currentWork: '报告 alice'
    })
    expect($officeProfiles.get().find(p => p.name === 'bob')).toMatchObject({
      label: 'bob',
      online: true,
      busy: false
    })
  })

  it('keeps gateway flag on online but stats idle-count ignores gateway', async () => {
    profilesState.list = [
      { name: 'alice', display_name: '爱丽丝', gateway_running: true },
      { name: 'bob', display_name: '', gateway_running: false }
    ]
    vi.mocked(getCronJobs).mockResolvedValue([])

    await refreshOfficeStore()

    expect($officeProfiles.get().find(p => p.name === 'alice')?.online).toBe(true)
    expect($officeProfiles.get().find(p => p.name === 'bob')?.online).toBe(false)
    // Both idle (not busy) → stats.online (idle count) = 2
    expect($stats.get().online).toBe(2)
    expect($stats.get().busy).toBe(0)
  })

  it('treats missing gateway_running as gateway-down without marking busy', async () => {
    profilesState.list = [{ name: 'alice', display_name: '爱丽丝' }]
    vi.mocked(getCronJobs).mockResolvedValue([])

    await refreshOfficeStore()

    expect($officeProfiles.get()[0]?.online).toBe(false)
    expect($officeProfiles.get()[0]?.busy).toBe(false)
    expect($stats.get().online).toBe(1)
  })

  it('keeps prior cron data when the cron fetch fails', async () => {
    $cronJobs.set([job({ id: 'keep', name: 'keep alice', enabled: true })])
    vi.mocked(getCronJobs).mockRejectedValue(new Error('down'))

    await refreshOfficeStore()

    expect($cronJobs.get().some(j => j.id === 'keep')).toBe(true)
    expect($officeProfiles.get().find(p => p.name === 'alice')?.busy).toBe(true)
  })

  it('keeps last profiles when refreshProfiles fails', async () => {
    vi.mocked(getCronJobs).mockResolvedValue([])
    refreshProfiles.mockRejectedValueOnce(new Error('profiles down'))

    await refreshOfficeStore()

    expect($officeProfiles.get().map(p => p.name)).toEqual(['alice', 'bob'])
  })
})

describe('dispatch helpers', () => {
  it('enqueues set_state and desk_visit through the scene bridge', () => {
    const enqueue = vi.fn(() => true)
    attachSceneEnqueue(enqueue)

    expect(dispatchSetState('alice', 'working', '任务中')).toBe(true)
    expect(enqueue).toHaveBeenCalledWith({
      type: 'set_state',
      profile: 'alice',
      state: 'working',
      task: '任务中'
    })

    expect(dispatchDeskVisit('alice', 'bob', 'hi')).toBe(true)
    expect(enqueue).toHaveBeenCalledWith({
      type: 'desk_visit',
      visitor: 'alice',
      host: 'bob',
      message: 'hi'
    })

    expect(dispatchDeskVisit('alice', 'alice')).toBe(false)
    expect(dispatchCelebrate('bob')).toBe(true)
    expect(enqueue).toHaveBeenCalledWith({ type: 'celebrate', target: 'bob' })
  })

  it('returns false when the scene bridge is detached', () => {
    expect(dispatchSetState('alice', 'online')).toBe(false)
  })

  it('dispatches playEmote through the scene bridge', () => {
    const play = vi.fn(() => true)
    attachScenePlayEmote(play)
    expect(dispatchPlayEmote('alice', 'emotes/wave')).toBe(true)
    expect(play).toHaveBeenCalledWith('alice', 'emotes/wave')
  })
})

describe('detectBoardEvents', () => {
  it('enqueues a desk_visit when a new job names a host profile', async () => {
    const enqueue = vi.fn(() => true)
    attachSceneEnqueue(enqueue)

    const first = job({ id: 'existing', name: '任务一', enabled: true })
    const fresh = job({ id: 'new-job', name: '报告 bob', enabled: true })
    vi.mocked(getCronJobs)
      .mockResolvedValueOnce([first])
      .mockResolvedValueOnce([first, fresh])

    await refreshOfficeStore()
    await refreshOfficeStore()

    expect(enqueue).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'desk_visit',
        host: 'bob',
        visitor: 'alice',
        message: '新任务: 报告 bob'
      })
    )
  })

  it('enqueues celebrate when a job last_run_at advances', async () => {
    const enqueue = vi.fn(() => true)
    attachSceneEnqueue(enqueue)

    const first = job({ id: 'run-job', name: '报告 bob', enabled: true, last_run_at: '100' })
    const after = job({ id: 'run-job', name: '报告 bob', enabled: true, last_run_at: '200' })
    vi.mocked(getCronJobs).mockResolvedValueOnce([first]).mockResolvedValueOnce([after])

    await refreshOfficeStore()
    await refreshOfficeStore()

    expect(enqueue).toHaveBeenCalledWith({ type: 'celebrate', target: 'bob' })
  })

  it('can cast a gateway-down profile as visitor', async () => {
    profilesState.list = [
      { name: 'alice', display_name: '爱丽丝', gateway_running: false },
      { name: 'bob', display_name: '', gateway_running: true }
    ]
    const enqueue = vi.fn(() => true)
    attachSceneEnqueue(enqueue)

    const first = job({ id: 'existing', name: '任务一', enabled: true })
    const fresh = job({ id: 'new-job', name: '报告 bob', enabled: true })
    vi.mocked(getCronJobs)
      .mockResolvedValueOnce([first])
      .mockResolvedValueOnce([first, fresh])

    await refreshOfficeStore()
    await refreshOfficeStore()

    expect(enqueue).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'desk_visit', host: 'bob', visitor: 'alice' })
    )
  })

  it('does not enqueue on first load (no previous snapshot)', async () => {
    const enqueue = vi.fn(() => true)
    attachSceneEnqueue(enqueue)
    vi.mocked(getCronJobs).mockResolvedValue([job({ name: '任务一', enabled: true })])

    await refreshOfficeStore()

    expect(enqueue).not.toHaveBeenCalled()
  })

  it('marks busy from kanban assignee and visits on new cards', async () => {
    const enqueue = vi.fn(() => true)
    attachSceneEnqueue(enqueue)
    vi.mocked(getCronJobs).mockResolvedValue([])
    vi.mocked(pluginRest)
      .mockResolvedValueOnce({ columns: [{ tasks: [] }] })
      .mockResolvedValueOnce({
        columns: [
          {
            tasks: [{ id: 'k1', title: '看板演示', status: 'running', assignee: 'bob' }]
          }
        ]
      })

    await refreshOfficeStore()
    expect($officeProfiles.get().find(p => p.name === 'bob')?.busy).toBe(false)

    await refreshOfficeStore()
    expect($officeProfiles.get().find(p => p.name === 'bob')?.busy).toBe(true)
    expect($officeProfiles.get().find(p => p.name === 'bob')?.currentWork).toBe('看板演示')
    expect($stats.get().openTasks).toBe(1)
    expect(enqueue).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'desk_visit',
        host: 'bob',
        visitor: 'alice',
        message: '新任务: 看板演示'
      })
    )
  })
})
