import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  $officeActivity,
  pushOfficeActivity,
  recordOfficeAction,
  resetOfficeActivity,
  summarizeOfficeAction
} from './activity'

vi.mock('@/i18n', () => ({
  translateNow: (key: string, ...args: unknown[]) => {
    if (key === 'office.activity.visit') return `${args[0]} visited ${args[1]}`
    if (key === 'office.activity.celebrate') return `${args[0]} done`
    if (key === 'office.activity.setState') return `${args[0]}=${args[1]}`
    return key
  }
}))

beforeEach(() => {
  resetOfficeActivity()
})

describe('office activity feed', () => {
  it('summarizes actions for the right-panel feed', () => {
    expect(summarizeOfficeAction({ type: 'desk_visit', visitor: 'a', host: 'b' })).toBe('a visited b')
    expect(summarizeOfficeAction({ type: 'celebrate', target: 'c' })).toBe('c done')
    expect(summarizeOfficeAction({ type: 'set_state', profile: 'a', state: 'online' })).toBe('a=online')
  })

  it('keeps a newest-first ring buffer', () => {
    for (let i = 0; i < 25; i++) {
      pushOfficeActivity('refresh', `n-${i}`, 1_000 + i)
    }
    const items = $officeActivity.get()
    expect(items).toHaveLength(20)
    expect(items[0]?.summary).toBe('n-24')
    expect(items[19]?.summary).toBe('n-5')
  })

  it('records scene actions onto the feed', () => {
    recordOfficeAction({ type: 'desk_visit', visitor: 'alice', host: 'bob', message: 'hi' })
    expect($officeActivity.get()[0]).toMatchObject({
      kind: 'desk_visit',
      summary: 'alice visited bob'
    })
  })
})
