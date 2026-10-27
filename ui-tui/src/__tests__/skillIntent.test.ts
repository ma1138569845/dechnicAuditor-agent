import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { JsonRpcGatewayError } from '@hermes/shared/json-rpc-channel'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createSlashHandler } from '../app/createSlashHandler.js'
import { submitPrompt, type SubmitPromptDeps } from '../app/submissionCore.js'
import { captureDestination } from '../app/submissionDestination.js'
import { patchUiState, resetUiState } from '../app/uiStore.js'
import type { GatewayClient } from '../gatewayClient.js'
import { type QueueItem, takeQueueItem } from '../hooks/useQueue.js'

const deps = (request: ReturnType<typeof vi.fn>): SubmitPromptDeps => ({
  appendMessage: vi.fn(),
  enqueue: vi.fn(),
  expand: value => value,
  gw: { request } as unknown as GatewayClient,
  setLastUserMsg: vi.fn(),
  sys: vi.fn()
})

describe('trusted learn tickets', () => {
  let taskHome = ''

  beforeEach(() => {
    resetUiState()
    patchUiState({ sid: 'runtime-1' })
    taskHome = mkdtempSync(join(tmpdir(), 'hermes-skill-intent-'))
    process.env.HERMES_HOME = taskHome
  })

  afterEach(() => {
    rmSync(taskHome, { force: true, recursive: true })
  })

  it('sends the ticket with the exact prompt but never journals it as replayable input', async () => {
    const request = vi.fn().mockResolvedValue({
      admission_id: 'submission-1',
      status: 'queued',
      target_profile_home: captureDestination().profileHome,
      target_session_id: 'stored-runtime-1'
    })

    const item: QueueItem = {
      destination: captureDestination(),
      display: 'expanded learn prompt',
      skillIntentTicket: 'opaque-ticket',
      submissionId: 'submission-1',
      text: 'expanded learn prompt'
    }

    submitPrompt('expanded learn prompt', deps(request), true, undefined, {
      queueItem: item,
      skipDetectDrop: true
    })

    await vi.waitFor(() => expect(request).toHaveBeenCalled())
    expect(request.mock.calls[0]?.[1]).toMatchObject({
      queued: true,
      skill_intent_ticket: 'opaque-ticket',
      text: 'expanded learn prompt'
    })

    const pendingDirectory = join(taskHome, 'tui-pending-inputs')
    const [record] = readdirSync(pendingDirectory)
    expect(JSON.parse(readFileSync(join(pendingDirectory, record!), 'utf8'))).not.toHaveProperty(
      'skillIntentTicket'
    )
  })

  it('does not infer trust from text and drops a spent ticket when the prompt is edited', () => {
    const request = vi.fn().mockResolvedValue({ status: 'streaming' })

    submitPrompt('[/learn] keep the audit checks', deps(request), true, undefined, {
      skipDetectDrop: true
    })

    expect(request.mock.calls[0]?.[1]).not.toHaveProperty('skill_intent_ticket')

    const queued: QueueItem[] = [
      {
        display: 'old prompt',
        skillIntentTicket: 'one-shot',
        text: 'old prompt'
      }
    ]

    const edited = takeQueueItem(queued, 0, 'changed prompt')
    expect(edited?.skillIntentTicket).toBeUndefined()
  })

  it('forwards a command.dispatch ticket to prompt.submit without changing the message', async () => {
    patchUiState({ sid: 'runtime-1' })

    const request = vi.fn((method: string) => {
      if (method === 'slash.exec') {
        return Promise.reject(
          new JsonRpcGatewayError(
            'skill command: use command.dispatch for /trusted-dispatch',
            { code: 4018 }
          )
        )
      }

      if (method === 'command.dispatch') {
        return Promise.resolve({
          message: 'expanded learn prompt',
          skill_intent_ticket: 'opaque-ticket',
          type: 'send'
        })
      }

      return Promise.resolve({})
    })

    const send = vi.fn()

    const ctx = {
      composer: {
        enqueue: vi.fn(),
        hasSelection: false,
        openEditor: vi.fn(),
        queueRef: { current: [] },
        selection: { copySelection: vi.fn() },
        setInput: vi.fn()
      },
      gateway: { gw: { request }, rpc: vi.fn() },
      local: {
        catalog: null,
        getHistoryItems: vi.fn(() => []),
        getLastUserMsg: vi.fn(() => ''),
        maybeWarn: vi.fn(),
        setCatalog: vi.fn()
      },
      session: {
        closeSession: vi.fn(),
        die: vi.fn(),
        dieWithCode: vi.fn(),
        guardBusySessionSwitch: vi.fn(() => false),
        newLiveSession: vi.fn(),
        newSession: vi.fn(),
        resetVisibleHistory: vi.fn(),
        resumeById: vi.fn(),
        setSessionStartedAt: vi.fn()
      },
      slashFlightRef: { current: 0 },
      transcript: {
        page: vi.fn(),
        panel: vi.fn(),
        send,
        setHistoryItems: vi.fn(),
        sys: vi.fn(),
        trimLastExchange: vi.fn(items => items)
      },
      voice: { setVoiceEnabled: vi.fn(), setVoiceRecordKey: vi.fn(), setVoiceTts: vi.fn() }
    }

    createSlashHandler(ctx as never)('/trusted-dispatch')

    await vi.waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        'expanded learn prompt',
        true,
        undefined,
        undefined,
        { attachments: undefined, skillIntentTicket: 'opaque-ticket' }
      )
    )
  })
})
