import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { EnergyAuditSettingsResponse } from '@/hermes'

import { EnergyAuditSettings } from './energy-audit-settings'

const getSettings = vi.fn()
const saveSettings = vi.fn()
const testConnection = vi.fn()
const resetSettings = vi.fn()
const confirm = vi.fn()

vi.mock('@/hermes', () => ({
  getEnergyAuditSettings: (...args: unknown[]) => getSettings(...args),
  saveEnergyAuditSettings: (...args: unknown[]) => saveSettings(...args),
  testEnergyAuditConnection: (...args: unknown[]) => testConnection(...args),
  resetEnergyAuditSettings: (...args: unknown[]) => resetSettings(...args)
}))

vi.mock('@/store/confirm', () => ({
  confirm: (...args: unknown[]) => confirm(...args)
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

vi.mock('@/store/settings-scope', () => ({
  $settingsScopeProfile: { get: () => 'audit', listen: () => () => undefined, subscribe: () => () => undefined }
}))

vi.mock('@nanostores/react', () => ({
  useStore: (store: { get: () => unknown }) => store.get()
}))

const LOADED: EnergyAuditSettingsResponse = {
  profile: 'audit',
  values: { host: 'db.internal', port: '5432', database: 'audit', user: 'reader', sslmode: 'require' },
  sources: { host: 'profile_config', password: 'environment' },
  file: {
    base_url: 'https://files.example.test/images',
    source: 'profile_config',
    environment_override: false
  },
  password_set: true,
  env_vars: { password: 'EA_PG_PASSWORD' },
  env_overrides: ['host']
}

beforeEach(() => {
  getSettings.mockResolvedValue(LOADED)
  saveSettings.mockResolvedValue({ ...LOADED, values: { ...LOADED.values, host: 'saved.internal' } })
  testConnection.mockResolvedValue({ ok: true, code: 'ok', message: 'connected', stages: {} })
  resetSettings.mockResolvedValue(LOADED)
  confirm.mockResolvedValue(true)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('EnergyAuditSettings', () => {
  it('loads effective values without prefilling the password', async () => {
    render(<EnergyAuditSettings />)

    expect(await screen.findByDisplayValue('db.internal')).toBeTruthy()
    expect(
      screen.getByText(
        'A process environment value still overrides Host. Saving or resetting does not change those effective values.'
      )
    ).toBeTruthy()
    expect((screen.getByPlaceholderText('Configured (empty keeps it)') as HTMLInputElement).value).toBe('')
  })

  it('saves typed fields and leaves an empty password unchanged', async () => {
    render(<EnergyAuditSettings />)
    fireEvent.change(await screen.findByDisplayValue('db.internal'), { target: { value: 'saved.internal' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(saveSettings).toHaveBeenCalledWith(
        expect.objectContaining({ host: 'saved.internal', password: '' }),
        'audit'
      )
    })
  })

  it('saves the attachment service URL separately from the database host', async () => {
    render(<EnergyAuditSettings />)
    const fileUrl = await screen.findByLabelText('Attachment file service URL')
    fireEvent.change(fileUrl, { target: { value: 'https://new-files.example.test/images/' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(saveSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          host: 'db.internal',
          file_base_url: 'https://new-files.example.test/images/',
          password: ''
        }),
        'audit'
      )
    })
  })

  it('shows when EA_FILE_BASE_URL controls the effective attachment address', async () => {
    getSettings.mockResolvedValueOnce({
      ...LOADED,
      env_overrides: [],
      file: {
        base_url: 'https://environment.example.test/images',
        source: 'environment',
        environment_override: true
      }
    })
    render(<EnergyAuditSettings />)

    expect(
      await screen.findByText(
        'A process environment value still overrides Attachment file service URL. Saving or resetting does not change those effective values.'
      )
    ).toBeTruthy()
  })

  it('disables attachment URL editing when an older backend omits file settings', async () => {
    getSettings.mockResolvedValueOnce({ ...LOADED, file: undefined })
    render(<EnergyAuditSettings />)

    const fileUrl = await screen.findByLabelText('Attachment file service URL')
    expect((fileUrl as HTMLInputElement).disabled).toBe(true)
    expect(
      screen.getByText('This backend does not support configuring the attachment file service URL.')
    ).toBeTruthy()
  })

  it('ignores settings loaded for the previous profile', async () => {
    let resolveFirst: ((value: EnergyAuditSettingsResponse) => void) | undefined
    getSettings.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveFirst = resolve
        })
    )
    getSettings.mockResolvedValueOnce({
      ...LOADED,
      values: { ...LOADED.values, host: 'fresh.internal' }
    })
    const view = render(<EnergyAuditSettings profile="first" />)
    await waitFor(() => expect(getSettings).toHaveBeenCalledTimes(1))
    view.rerender(<EnergyAuditSettings profile="other" />)
    expect(await screen.findByDisplayValue('fresh.internal')).toBeTruthy()
    resolveFirst?.(LOADED)

    await waitFor(() => expect(screen.queryByDisplayValue('db.internal')).toBeNull())
    expect(screen.getByDisplayValue('fresh.internal')).toBeTruthy()
  })

  it('asks before resetting and does not reset when cancelled', async () => {
    confirm.mockResolvedValue(false)
    render(<EnergyAuditSettings />)
    fireEvent.click(await screen.findByRole('button', { name: 'Reset non-secret fields' }))

    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(resetSettings).not.toHaveBeenCalled()
  })
})
