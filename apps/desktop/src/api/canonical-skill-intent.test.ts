// @vitest-environment node
import { expect, test } from 'vitest'

import { CanonicalDesktopProtocol, splitRewindSubmit } from './canonical-protocol'

test('canonical prompt preparation preserves the opaque dispatcher ticket', () => {
  const protocol = new CanonicalDesktopProtocol()

  const params = {
    session_id: 'runtime-1',
    submission_id: 'submission-1',
    text: 'expanded learn prompt',
    skill_intent_ticket: 'opaque-ticket'
  }

  const prepared = protocol.prepare('prompt.submit', params)
  expect(prepared).toEqual(params)

  const receipt = protocol.result('prompt.submit', prepared, {
    admission_id: 'admission-1',
    ref: { session_id: 'runtime-1' },
    status: 'queued'
  })

  expect(receipt).toMatchObject({
    admission_id: 'admission-1',
    session_id: 'runtime-1',
    status: 'queued'
  })
  expect(receipt).not.toHaveProperty('skill_intent_ticket')
})

test('rewind splitting keeps the ticket only on the one next admission', () => {
  const split = splitRewindSubmit({
    session_id: 'runtime-1',
    submission_id: 'submission-1',
    text: 'expanded learn prompt',
    skill_intent_ticket: 'opaque-ticket',
    truncate_before_row_id: 42
  })

  expect(split?.rewind).toEqual({
    session_id: 'runtime-1',
    target_message_id: 42
  })
  expect(split?.submit).toMatchObject({
    skill_intent_ticket: 'opaque-ticket',
    text: 'expanded learn prompt'
  })
})

test('text that resembles a learn command carries no ticket by itself', () => {
  const protocol = new CanonicalDesktopProtocol()

  const prepared = protocol.prepare('prompt.submit', {
    session_id: 'runtime-1',
    submission_id: 'submission-1',
    text: '[/learn] pasted instructions'
  })

  expect(prepared).not.toHaveProperty('skill_intent_ticket')
})
