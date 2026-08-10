import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { OnlyOfficeSettings } from './onlyoffice-settings'

const getOnlyOffice = vi.fn()
const setOnlyOffice = vi.fn()
const applyOnlyOffice = vi.fn()
const clearOnlyOffice = vi.fn()

const ENABLED_STATE: OnlyOfficeSettingsState = {
  saved: {
    dsUrl: 'http://10.10.2.55:8090',
    callbackHost: '192.168.0.238',
    previewPort: '39250',
    jwtSecretConfigured: true
  },
  effective: {
    enabled: true,
    source: 'config',
    dsUrl: 'http://10.10.2.55:8090',
    callbackHost: '192.168.0.238',
    previewPort: '39250',
    jwtSecretConfigured: true
  }
}

const DISABLED_STATE: OnlyOfficeSettingsState = {
  saved: { jwtSecretConfigured: false },
  effective: { enabled: false, source: 'none', jwtSecretConfigured: false }
}

function mockBridge(state: OnlyOfficeSettingsState = ENABLED_STATE) {
  getOnlyOffice.mockResolvedValue(state)
  setOnlyOffice.mockImplementation(async (config: OnlyOfficeConfigInput) => ({
    saved: {
      dsUrl: config.dsUrl,
      callbackHost: config.callbackHost,
      previewPort: config.previewPort,
      jwtSecretConfigured: Boolean(config.jwtSecret)
    },
    effective: {
      enabled: Boolean(config.dsUrl && config.jwtSecret),
      source: 'config' as const,
      dsUrl: config.dsUrl,
      callbackHost: config.callbackHost,
      previewPort: config.previewPort,
      jwtSecretConfigured: Boolean(config.jwtSecret)
    }
  }))
  applyOnlyOffice.mockImplementation(setOnlyOffice.getMockImplementation()!)
  clearOnlyOffice.mockResolvedValue(DISABLED_STATE)

  Object.defineProperty(window, 'hermesDesktop', {
    configurable: true,
    value: {
      settings: {
        onlyoffice: {
          get: getOnlyOffice,
          set: setOnlyOffice,
          apply: applyOnlyOffice,
          clear: clearOnlyOffice
        }
      }
    }
  })
}

beforeEach(() => {
  getOnlyOffice.mockReset()
  setOnlyOffice.mockReset()
  applyOnlyOffice.mockReset()
  clearOnlyOffice.mockReset()
  mockBridge()
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('OnlyOfficeSettings', () => {
  it('loads saved values and shows the enabled status', async () => {
    render(<OnlyOfficeSettings />)

    expect(await screen.findByText('Enabled')).toBeTruthy()
    expect((screen.getByPlaceholderText('http://10.10.2.55:8090') as HTMLInputElement).value).toBe(
      'http://10.10.2.55:8090'
    )
    expect((screen.getByPlaceholderText('e.g. 192.168.0.238 (optional)') as HTMLInputElement).value).toBe(
      '192.168.0.238'
    )
    // The secret is never echoed back — the panel only shows a "configured"
    // placeholder on the password field.
    expect((screen.getByPlaceholderText('Configured (empty keeps it, type to change)') as HTMLInputElement).value).toBe(
      ''
    )
  })

  it('shows the disabled warning when OnlyOffice is not enabled', async () => {
    getOnlyOffice.mockResolvedValue(DISABLED_STATE)
    mockBridge(DISABLED_STATE)
    render(<OnlyOfficeSettings />)

    expect(await screen.findByText('Disabled')).toBeTruthy()
    expect(screen.getByText(/OnlyOffice is disabled/i)).toBeTruthy()
  })

  it('save calls set with the form values and an empty secret keeps the stored one', async () => {
    render(<OnlyOfficeSettings />)
    await screen.findByText('Enabled')

    fireEvent.change(screen.getByPlaceholderText('http://10.10.2.55:8090'), {
      target: { value: 'http://new.example.com:8090' }
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(setOnlyOffice).toHaveBeenCalledWith({
        dsUrl: 'http://new.example.com:8090',
        jwtSecret: '',
        callbackHost: '192.168.0.238',
        previewPort: '39250'
      })
    })
  })

  it('save & restart backend calls apply', async () => {
    render(<OnlyOfficeSettings />)
    await screen.findByText('Enabled')

    fireEvent.click(screen.getByRole('button', { name: 'Save & restart backend' }))

    await waitFor(() => {
      expect(applyOnlyOffice).toHaveBeenCalled()
    })
  })

  it('clear config calls clear and resets the form', async () => {
    render(<OnlyOfficeSettings />)
    await screen.findByText('Enabled')

    fireEvent.click(screen.getByRole('button', { name: 'Clear config' }))

    await waitFor(() => {
      expect(clearOnlyOffice).toHaveBeenCalled()
    })
    expect(await screen.findByText('Disabled')).toBeTruthy()
  })
})
