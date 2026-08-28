import { describe, expect, it } from 'vitest'

import { resolveOfficePresence } from './presence'

describe('resolveOfficePresence', () => {
  it('is work-centric: busy or idle only', () => {
    expect(resolveOfficePresence(false)).toBe('idle')
    expect(resolveOfficePresence(true)).toBe('busy')
  })
})
