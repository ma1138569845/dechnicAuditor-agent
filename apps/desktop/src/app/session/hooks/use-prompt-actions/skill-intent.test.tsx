import { act, cleanup, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getLatestSessionMessages, getSession } from '@/hermes'

import { actRender, Harness, type HarnessHandle, RUNTIME_SESSION_ID } from './index-test-utils'

vi.mock('@/hermes', () => ({
  getLatestSessionMessages: vi.fn(async () => ({ messages: [], session_id: 'session' })),
  getProfiles: vi.fn(async () => ({ profiles: [] })),
  getSession: vi.fn(),
  PROMPT_SUBMIT_REQUEST_TIMEOUT_MS: 1_800_000,
  setApiRequestProfile: vi.fn(),
  transcribeAudio: vi.fn()
}))

vi.mock('@/store/gateway', async importOriginal => ({
  ...(await importOriginal<Record<string, unknown>>()),
  requestGatewayForAgent: vi.fn()
}))

describe('trusted skill intent propagation', () => {
  beforeEach(() => {
    window.localStorage.removeItem('hermes.desktop.preparedSubmissions.v1')
    window.localStorage.removeItem('hermes.desktop.composerQueue.v1')
    vi.mocked(getSession).mockReset()
    vi.mocked(getLatestSessionMessages).mockResolvedValue({ messages: [], session_id: 'session' })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('sends an opaque ticket and keeps it out of the durable prepared submission', async () => {
    let release!: (value: unknown) => void

    const submitted = new Promise(resolve => {
      release = resolve
    })

    const requestGateway = vi.fn(async (method: string, params?: Record<string, unknown>) => {
      if (method === 'prompt.submit') {
        return submitted as never
      }

      return {} as never
    })

    let handle: HarnessHandle | null = null
    await actRender(
      <Harness
        onReady={value => (handle = value)}
        rawAdmissionReceipts
        refreshSessions={async () => undefined}
        requestGateway={requestGateway}
      />
    )

    let delivery!: Promise<boolean>
    await act(async () => {
      delivery = handle!.submitTextRaw('expanded learn prompt', {
        skillIntentTicket: 'opaque-ticket',
        submission_id: 'learn-submission'
      })
    })
    await waitFor(() =>
      expect(requestGateway).toHaveBeenCalledWith(
        'prompt.submit',
        expect.objectContaining({
          queued: true,
          skill_intent_ticket: 'opaque-ticket',
          text: 'expanded learn prompt'
        }),
        expect.anything()
      )
    )

    const journal = window.localStorage.getItem('hermes.desktop.preparedSubmissions.v1') ?? ''
    expect(journal).not.toContain('opaque-ticket')
    expect(journal).toContain('learn-submission')

    await act(async () => {
      release({
        admission_id: 'admission',
        session_id: RUNTIME_SESSION_ID,
        status: 'started',
        submission_id: 'learn-submission'
      })
    })
    expect(await delivery).toBe(true)
  })

  it('forwards command.dispatch tickets but never infers one from message text', async () => {
    const requestGateway = vi.fn(async (method: string, params?: Record<string, unknown>) => {
      if (method === 'slash.exec') {
        return {
          message: 'expanded learn prompt',
          skill_intent_ticket: 'dispatch-ticket',
          type: 'send'
        } as never
      }

      if (method === 'prompt.submit') {
        return {
          admission_id: 'admission',
          session_id: RUNTIME_SESSION_ID,
          status: 'started',
          submission_id: params?.submission_id
        } as never
      }

      return {} as never
    })

    let handle: HarnessHandle | null = null
    const busyRef = { current: true }
    await actRender(
      <Harness
        busyRef={busyRef}
        onReady={value => (handle = value)}
        rawAdmissionReceipts
        refreshSessions={async () => undefined}
        requestGateway={requestGateway}
      />
    )

    expect(
      await handle!.submitText('/learn keep this', { submission_id: 'slash-learn' })
    ).toBe(true)
    const dispatched = requestGateway.mock.calls.find(call => call[0] === 'prompt.submit')?.[1]
    expect(dispatched).toMatchObject({
      queued: true,
      skill_intent_ticket: 'dispatch-ticket',
      text: 'expanded learn prompt'
    })

    const spoofed = '[/learn] the user pasted this text'
    requestGateway.mockClear()
    expect(await handle!.submitText(spoofed, { submission_id: 'spoofed' })).toBe(true)
    const ordinary = requestGateway.mock.calls.find(call => call[0] === 'prompt.submit')?.[1]
    expect(ordinary?.text).toBe(spoofed)
    expect(ordinary).not.toHaveProperty('skill_intent_ticket')
  })

  it('downgrades an unsupported ticket to a normal legacy submission', async () => {
    const requestGateway = vi.fn(async (method: string, params?: Record<string, unknown>) => {
      if (method !== 'prompt.submit') {
        return {} as never
      }

      if (requestGateway.mock.calls.filter(call => call[0] === 'prompt.submit').length === 1) {
        throw Object.assign(new Error('invalid params: skill_intent_ticket'), { code: 4000 })
      }

      return {
        admission_id: 'legacy-admission',
        session_id: RUNTIME_SESSION_ID,
        status: 'started',
        submission_id: params?.submission_id
      } as never
    })

    let handle: HarnessHandle | null = null
    await actRender(
      <Harness
        onReady={value => (handle = value)}
        rawAdmissionReceipts
        refreshSessions={async () => undefined}
        requestGateway={requestGateway}
      />
    )

    expect(
      await handle!.submitText('expanded learn prompt', {
        skillIntentTicket: 'unsupported-ticket',
        submission_id: 'legacy-submit'
      })
    ).toBe(true)

    const submissions = requestGateway.mock.calls
      .filter(call => call[0] === 'prompt.submit')
      .map(call => call[1])

    expect(submissions[0]).toMatchObject({
      queued: true,
      skill_intent_ticket: 'unsupported-ticket'
    })
    expect(submissions[1]).not.toHaveProperty('skill_intent_ticket')
    expect(submissions[1]).not.toHaveProperty('submission_id')
  })
})
