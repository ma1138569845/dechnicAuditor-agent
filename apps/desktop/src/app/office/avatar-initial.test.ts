import { describe, expect, it } from 'vitest'

import { avatarInitial } from './avatar-initial'

describe('avatarInitial', () => {
  it('uses the first latin letter uppercased', () => {
    expect(avatarInitial('default')).toBe('D')
    expect(avatarInitial('author')).toBe('A')
  })

  it('keeps the first han character', () => {
    expect(avatarInitial('爱丽丝')).toBe('爱')
  })

  it('falls back for empty input', () => {
    expect(avatarInitial('')).toBe('?')
    expect(avatarInitial('   ')).toBe('?')
  })
})
