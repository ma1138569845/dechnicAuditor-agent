import { QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { SkillInfo, SkillProposalDetail, SkillProposalListResponse, SkillProposalSummary } from '@/types/hermes'

const mocks = vi.hoisted(() => ({
  approveSkillProposal: vi.fn(),
  getSkillProposal: vi.fn(),
  getSkillProposals: vi.fn(),
  notify: vi.fn(),
  notifyError: vi.fn(),
  rejectSkillProposal: vi.fn()
}))

vi.mock('@/api/skills', () => ({
  approveSkillProposal: mocks.approveSkillProposal,
  getSkillProposal: mocks.getSkillProposal,
  getSkillProposals: mocks.getSkillProposals,
  rejectSkillProposal: mocks.rejectSkillProposal
}))

vi.mock('@/app/capabilities/catalog/skill-catalog', () => ({
  SkillCatalog: ({ skills }: { skills: SkillInfo[] }) => (
    <div data-testid="installed-catalog">installed:{skills.length}</div>
  )
}))

vi.mock('@/store/notifications', () => ({
  notify: mocks.notify,
  notifyError: mocks.notifyError
}))

import { queryClient } from '@/lib/query-client'

import { PendingProposals } from './pending-proposals'
import { skillProposalDetailQueryKey, skillProposalsQueryKey } from './proposal-data'
import { SkillsTab } from './skills-tab'

const profile = 'alpha'
const reviewHash = 'sha256:' + 'r'.repeat(64)
const baseHash = 'sha256:' + 'b'.repeat(64)

function proposal(overrides: Partial<SkillProposalDetail> = {}): SkillProposalDetail {
  return {
    schema_version: 2,
    id: 'skp_audit',
    status: 'pending',
    revision: 3,
    review_hash: reviewHash,
    base_hash: baseHash,
    created_at: 1_700_000_000,
    last_seen_at: 1_700_000_200,
    expires_at: 1_700_086_400,
    evidence_count: 2,
    target: { skill: 'energy-audit-report' },
    operation: { action: 'patch', file_path: 'references/chapter1.md' },
    preview: {
      summary: 'patch energy-audit-report / references/chapter1.md',
      diff: '@@ -1 +1 @@\n-Verify one source.\n+Verify two sources.',
      lint: [{ severity: 'warning', rule: 'evidence', message: 'Evidence is incomplete.' }],
      security: { verdict: 'safe', findings: [] }
    },
    conflict: null,
    evidence: [
      {
        kind: 'user_correction',
        message_refs: [2, 7],
        reason: 'The user corrected the source-verification workflow.'
      }
    ],
    ...overrides
  }
}

function list(rows: SkillProposalSummary[] = [proposal()]): SkillProposalListResponse {
  return {
    proposals: rows,
    count: rows.length,
    queue: {
      pending_count: rows.length,
      max_pending: 25,
      over_limit: false,
      targets_over_limit: [],
      earliest_expires_at: rows[0]?.expires_at ?? null,
      broken_count: 0
    }
  }
}

function renderPending(
  data: SkillProposalListResponse | undefined,
  options: {
    error?: Error | null
    onRetry?: () => void
    pending?: boolean
  } = {}
) {
  if (data) {
    queryClient.setQueryData(skillProposalsQueryKey(profile, 'pending'), data)
  }

  return render(
    <QueryClientProvider client={queryClient}>
      <PendingProposals
        data={data}
        error={options.error ?? null}
        onRetry={options.onRetry ?? (() => undefined)}
        pending={options.pending ?? false}
        profile={profile}
      />
    </QueryClientProvider>
  )
}

function renderSkills(initialProfile = profile) {
  function Harness() {
    const [currentProfile, setCurrentProfile] = useState(initialProfile)

    return (
      <>
        <button onClick={() => setCurrentProfile('beta')} type="button">
          Change profile
        </button>
        <QueryClientProvider client={queryClient}>
          <SkillsTab
            onRefresh={() => undefined}
            profile={currentProfile}
            query=""
            skills={[{ category: 'general', description: 'Installed', enabled: true, name: 'installed-skill' }]}
          />
        </QueryClientProvider>
      </>
    )
  }

  return render(<Harness />)
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void

  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })

  return { promise, reject, resolve }
}

beforeEach(() => {
  queryClient.clear()
  queryClient.setDefaultOptions({
    queries: {
      retry: false,
      staleTime: Number.POSITIVE_INFINITY
    }
  })

  vi.stubGlobal(
    'ResizeObserver',
    class ResizeObserver {
      disconnect() {}
      observe() {}
      unobserve() {}
    }
  )
  Element.prototype.scrollIntoView = vi.fn()
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.releasePointerCapture = vi.fn()

  mocks.getSkillProposals.mockResolvedValue(list())
  mocks.getSkillProposal.mockImplementation((id: string) =>
    Promise.resolve(
      proposal({
        id,
        target: { skill: id === 'skp_second' ? 'report-qa' : 'energy-audit-report' }
      })
    )
  )
  mocks.approveSkillProposal.mockResolvedValue({ ok: true })
  mocks.rejectSkillProposal.mockResolvedValue({ ok: true })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('Pending proposals', () => {
  it('updates the passive badge without switching tabs, opening a dialog, or moving focus', async () => {
    mocks.getSkillProposals.mockResolvedValueOnce(list([proposal()]))
    renderSkills()

    const installed = await screen.findByRole('button', { name: 'Installed' })
    await screen.findByRole('button', { name: 'Pending (1)' })
    installed.focus()

    act(() => {
      queryClient.setQueryData(
        skillProposalsQueryKey(profile, 'pending'),
        list([proposal(), proposal({ id: 'skp_second', target: { skill: 'report-qa' } })])
      )
    })

    await screen.findByRole('button', { name: 'Pending (2)' })
    expect(installed.getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('installed-catalog').textContent).toContain('installed:1')
    expect(screen.queryByRole('dialog')).toBeNull()
    // eslint-disable-next-line no-restricted-globals -- asserting focus requires the live document
    expect(document.activeElement).toBe(installed)
  })

  it('renders loading, error, and empty states with their own recovery affordances', async () => {
    const loading = renderPending(undefined, { pending: true })
    expect(screen.getByRole('status', { name: 'Loading pending proposals…' })).toBeTruthy()
    loading.unmount()

    const retry = vi.fn()
    const failed = renderPending(undefined, { error: new Error('backend unavailable'), onRetry: retry })
    expect(screen.getByText('Pending proposals failed to load')).toBeTruthy()
    expect(screen.getByText('backend unavailable')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(retry).toHaveBeenCalledTimes(1)
    failed.unmount()

    renderPending(list([]))
    expect(await screen.findByText('No pending proposals')).toBeTruthy()
    expect(screen.getByText(/explicit evidence/i)).toBeTruthy()
  })

  it('shows capacity, warning, conflict, security, duplicate, and expiry states without mutating selection', async () => {
    const row = proposal({
      id: 'skp_risky',
      expires_at: 1_700_090_000,
      conflict: 'anchor_stale',
      preview: {
        summary: 'patch energy-audit-report',
        diff: '--- old\n+++ new\n-old\n+new',
        lint: [{ severity: 'warning', message: 'One warning' }],
        security: { verdict: 'unavailable', findings: [] }
      },
      related: {
        possible_duplicates: [{ id: 'skp_duplicate', reason: 'same target' }],
        overlap_count: 1
      }
    })

    const response = list([row])
    response.queue = {
      pending_count: 27,
      max_pending: 25,
      over_limit: true,
      targets_over_limit: [{ target: 'energy-audit-report', pending_count: 4, max_pending: 3 }],
      earliest_expires_at: 1_700_090_000,
      broken_count: 2
    }
    mocks.getSkillProposal.mockResolvedValue(row)

    renderPending(response)

    expect(await screen.findByText(/27 pending proposals exceed the limit of 25/)).toBeTruthy()
    expect(screen.getByText(/1 target queue is over capacity/)).toBeTruthy()
    expect(screen.getByText(/2 unreadable proposal records/)).toBeTruthy()
    expect(screen.getByText('Target changed')).toBeTruthy()
    expect(await screen.findByText('Security results unavailable')).toBeTruthy()
    expect(screen.getByText('Possible duplicate: skp_duplicate')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /merge/i })).toBeNull()
    expect((screen.getByRole('button', { name: 'Approve write' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('keeps v1 read and reject available while permanently disabling approval', async () => {
    const legacy = proposal({
      id: 'legacy1',
      schema_version: 1,
      revision: 1,
      review_hash: null,
      base_hash: null,
      legacy_reason: 'legacy_pending_requires_explicit_edit',
      target: { skill: 'legacy-skill' },
      preview: {
        summary: 'create legacy-skill',
        diff: '+ legacy content',
        lint: [],
        security: { verdict: 'safe', findings: [] }
      }
    })

    mocks.getSkillProposal.mockResolvedValue(legacy)

    renderPending(list([legacy]))

    expect(await screen.findByText('Legacy pending write')).toBeTruthy()
    expect(((await screen.findByRole('button', { name: 'Approve write' })) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('button', { name: 'Review as explicit edit' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Reject proposal' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reject proposal' }))

    await waitFor(() => expect(mocks.rejectSkillProposal).toHaveBeenCalledWith('legacy1', null, profile))
    expect(mocks.approveSkillProposal).not.toHaveBeenCalled()
  })

  it('explains an expired proposal and keeps only cleanup available', async () => {
    const expired = proposal({ status: 'expired' })
    mocks.getSkillProposal.mockResolvedValue(expired)

    renderPending(list([expired]))

    expect(await screen.findByText('Expired')).toBeTruthy()
    expect(screen.getByText(/expired before it was approved/i)).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Approve write' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Reject proposal' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('moves selection with arrows, focuses the primary action on Enter, and cancels the confirm with Escape', async () => {
    const first = proposal()
    const second = proposal({ id: 'skp_second', target: { skill: 'report-qa' }, last_seen_at: 1_699_999_000 })
    mocks.getSkillProposal.mockImplementation((id: string) => Promise.resolve(id === 'skp_second' ? second : first))

    renderPending(list([first, second]))

    const listbox = await screen.findByRole('listbox', { name: 'Pending proposal queue' })
    fireEvent.keyDown(listbox, { key: 'ArrowDown' })
    await waitFor(() =>
      expect(screen.getByRole('option', { name: /report-qa/i }).getAttribute('aria-selected')).toBe('true')
    )

    const approve = await screen.findByRole('button', { name: 'Approve write' })
    fireEvent.keyDown(listbox, { key: 'Enter' })
    await waitFor(() =>
      // eslint-disable-next-line no-restricted-globals -- asserting focus requires the live document
      expect(document.activeElement).toBe(approve)
    )
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(mocks.approveSkillProposal).not.toHaveBeenCalled()

    fireEvent.click(approve)
    expect(await screen.findByRole('dialog')).toBeTruthy()
    fireEvent.keyDown(window.document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(mocks.approveSkillProposal).not.toHaveBeenCalled()
  })

  it('removes optimistically only after confirmation and restores the full row when the API fails', async () => {
    mocks.approveSkillProposal.mockRejectedValue(new Error('409: {"error":"apply_failed","message":"disk offline"}'))
    renderPending(list())

    await screen.findByText('energy-audit-report')
    fireEvent.click(await screen.findByRole('button', { name: 'Approve write' }))
    const dialog = await screen.findByRole('dialog')
    expect(queryClient.getQueryData<SkillProposalListResponse>(skillProposalsQueryKey(profile, 'pending'))).toBeTruthy()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve write' }))
    await waitFor(() => {
      expect(
        queryClient.getQueryData<SkillProposalListResponse>(skillProposalsQueryKey(profile, 'pending'))?.count
      ).toBe(0)
    })

    await waitFor(() => expect(screen.getByText(/disk offline/)).toBeTruthy())
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.getByRole('option', { name: /energy-audit-report/i })).toBeTruthy()
    expect(mocks.approveSkillProposal).toHaveBeenCalledTimes(1)
    expect(mocks.notifyError).toHaveBeenCalledTimes(1)
  })

  it('refreshes a stale review and never retries it automatically', async () => {
    mocks.approveSkillProposal.mockRejectedValue(
      new Error('409: {"error":"review_hash_mismatch","current_revision":4,"current_review_hash":"sha256:new"}')
    )
    renderPending(list())

    const approve = await screen.findByRole('button', { name: 'Approve write' })
    const callsBefore = mocks.getSkillProposal.mock.calls.length
    fireEvent.click(approve)
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve write' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByText(/Content or validation results changed/)).toBeTruthy()
    await waitFor(() => expect(mocks.getSkillProposal.mock.calls.length).toBeGreaterThan(callsBefore))
    expect(mocks.approveSkillProposal).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('option', { name: /energy-audit-report/i })).toBeTruthy()
  })

  it('remounts the proposal surface so a profile change discards confirmation and in-flight state', async () => {
    const pendingApproval = deferred<{ ok: true }>()
    mocks.approveSkillProposal.mockReturnValueOnce(pendingApproval.promise)
    renderSkills()

    fireEvent.click(await screen.findByRole('button', { name: 'Pending (1)' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Approve write' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve write' }))

    mocks.getSkillProposals.mockResolvedValue(list([]))
    fireEvent.click(screen.getByText('Change profile'))
    await screen.findByRole('button', { name: 'Installed' })
    expect(screen.queryByRole('dialog')).toBeNull()

    await act(async () => pendingApproval.resolve({ ok: true }))
    expect(mocks.notify).not.toHaveBeenCalled()
    expect(queryClient.getQueryData(skillProposalDetailQueryKey(profile, 'skp_audit'))).toBeUndefined()
  })
})
