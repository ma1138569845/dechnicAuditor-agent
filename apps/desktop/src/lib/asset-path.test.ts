import { describe, expect, it } from 'vitest'

import { assetPath } from './asset-path'

describe('assetPath', () => {
  it('prefixes with BASE_URL and strips a leading slash', () => {
    expect(assetPath('/assets/office/office.png', './')).toBe('./assets/office/office.png')
    expect(assetPath('assets/office/office.png', './')).toBe('./assets/office/office.png')
  })

  it('works with an absolute http base (dev / hosted)', () => {
    expect(assetPath('/assets/office/desk.png', '/')).toBe('/assets/office/desk.png')
    expect(assetPath('assets/office/chair.png', 'https://app.example/')).toBe(
      'https://app.example/assets/office/chair.png',
    )
  })

  it('never emits a root-absolute path when base is relative (packaged Electron)', () => {
    const url = assetPath('/assets/office/office.png', './')
    expect(url.startsWith('/')).toBe(false)
    expect(url.startsWith('./')).toBe(true)
  })
})
