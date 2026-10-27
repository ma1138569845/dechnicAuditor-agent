import { afterEach, describe, expect, it, vi } from 'vitest'

import { approveSkillProposal, getSkillProposals, rejectSkillProposal } from '@/api/skills'
import type { SkillProposalSummary } from '@/types/hermes'

import {
  isSkillProposalApprovable,
  normalizeSkillProposalDetail,
  normalizeSkillProposalList,
  skillProposalDetailQueryKey,
  skillProposalErrorCode,
  skillProposalsQueryKey,
  sortSkillProposals
} from './proposal-data'

const profile = 'default'
const reviewHash = 'sha256:' + 'r'.repeat(64)
const baseHash = 'sha256:' + 'b'.repeat(64)

function rawProposal(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 2,
    id: 'skp_a',
    status: 'pending',
    revision: 3,
    review_hash: reviewHash,
    base_hash: baseHash,
    created_at: 1_700_000_000,
    updated_at: 1_700_000_100,
    last_seen_at: 1_700_000_200,
    expires_at: 1_700_086_400,
    target: { name: 'energy-audit-report', names: ['energy-audit-report'] },
    operation: {
      action: 'patch',
      name: 'energy-audit-report',
      file_path: 'references/chapter1.md',
      patch: '@@ -1 +1 @@\n-Verify one source.\n+Verify two sources.'
    },
    evidence: [
      {
        kind: 'user_correction',
        message_refs: [2, 7],
        reason: 'The user corrected the source-verification workflow.'
      }
    ],
    lint: [{ severity: 'warning', rule: 'report-evidence', message: 'Evidence is incomplete.' }],
    security: { verdict: 'safe', findings: [] },
    conflict: null,
    related: {
      possible_duplicates: [{ id: 'skp_duplicate', reason: 'same target' }],
      overlap_count: 1
    },
    ...overrides
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('skill proposal data', () => {
  it('keeps profile and proposal id in separate cache scopes', () => {
    expect(skillProposalsQueryKey(profile, 'pending')).toEqual(['skill-proposals', 'default', 'pending'])
    expect(skillProposalDetailQueryKey(profile, 'skp_a')).toEqual(['skill-proposal', 'default', 'skp_a'])
  })

  it('sorts conflict before warnings and then newest', () => {
    const rows = [
      { id: 'clean', conflict: null, preview: { lint: [] }, last_seen_at: 1 },
      { id: 'old-conflict', conflict: 'target_changed', preview: { lint: [] }, last_seen_at: 1 },
      {
        id: 'warning',
        conflict: null,
        preview: { lint: [{ severity: 'warning' }] },
        last_seen_at: 2
      },
      { id: 'new-conflict', conflict: 'anchor_stale', preview: { lint: [] }, last_seen_at: 3 }
    ] as unknown as SkillProposalSummary[]

    expect(sortSkillProposals(rows).map(row => row.id)).toEqual(['new-conflict', 'old-conflict', 'warning', 'clean'])
  })

  it('normalizes the real backend target, evidence, lint, and operation-derived diff shape', async () => {
    const normalized = normalizeSkillProposalList({
      proposals: [rawProposal()],
      count: 1,
      queue: {
        pending_count: 1,
        max_pending: 25,
        over_limit: false,
        targets_over_limit: 1,
        earliest_expires_at: 1_700_086_400,
        broken_count: 0
      }
    })

    expect(normalized.proposals[0]).toMatchObject({
      id: 'skp_a',
      evidence_count: 1,
      target: { skill: 'energy-audit-report' },
      preview: {
        summary: 'patch energy-audit-report / references/chapter1.md',
        diff: '@@ -1 +1 @@\n-Verify one source.\n+Verify two sources.',
        lint: [{ severity: 'warning' }]
      }
    })
    expect(normalized.queue.targets_over_limit).toHaveLength(1)
  })

  it('rejects a v2 query response without a review hash instead of inventing one', () => {
    expect(() => normalizeSkillProposalDetail(rawProposal({ review_hash: null }))).toThrow(/review_hash/)
  })

  it('maps v1 records to immutable legacy state without fabricating hashes', () => {
    const normalized = normalizeSkillProposalDetail({
      schema_version: 1,
      id: 'legacy1',
      status: 'pending',
      revision: 1,
      review_hash: null,
      base_hash: null,
      created_at: 1_700_000_000,
      expires_at: 1_700_086_400,
      target: { name: 'legacy-skill' },
      action: 'create',
      payload: {
        action: 'create',
        name: 'legacy-skill',
        content: '---\nname: legacy-skill\n---\n'
      }
    })

    expect(normalized).toMatchObject({
      schema_version: 1,
      legacy_reason: 'legacy_pending_requires_explicit_edit',
      review_hash: null,
      base_hash: null,
      target: { skill: 'legacy-skill' }
    })
    expect(isSkillProposalApprovable(normalized)).toBe(false)
  })

  it('rejects an inconsistent list count', () => {
    expect(() =>
      normalizeSkillProposalList({
        proposals: [rawProposal()],
        count: 2,
        queue: {
          pending_count: 1,
          max_pending: 25,
          over_limit: false,
          targets_over_limit: 0,
          earliest_expires_at: null,
          broken_count: 0
        }
      })
    ).toThrow(/count/)
  })

  it('blocks approval for conflicts, blocking lint, and unavailable security', () => {
    const safe = normalizeSkillProposalDetail(rawProposal())
    const changed = normalizeSkillProposalDetail(rawProposal({ conflict: 'target_changed' }))

    const lintBlocked = normalizeSkillProposalDetail(
      rawProposal({ lint: [{ severity: 'error', message: 'invalid frontmatter' }] })
    )

    const securityBlocked = normalizeSkillProposalDetail(
      rawProposal({ security: { verdict: 'unavailable', findings: [] } })
    )

    expect(isSkillProposalApprovable(safe)).toBe(true)
    expect(isSkillProposalApprovable(changed)).toBe(false)
    expect(isSkillProposalApprovable(lintBlocked)).toBe(false)
    expect(isSkillProposalApprovable(securityBlocked)).toBe(false)
  })

  it('extracts stable proposal errors from the desktop HTTP error message', () => {
    expect(
      skillProposalErrorCode(
        new Error('409: {"error":"review_hash_mismatch","current_revision":4,"current_review_hash":"sha256:new"}')
      )
    ).toBe('review_hash_mismatch')
    expect(skillProposalErrorCode(new Error('409: {"error":"review_refresh_required"}'))).toBe(
      'review_refresh_required'
    )
    expect(skillProposalErrorCode(new Error('network down'))).toBeNull()
  })

  it('approves with exactly revision, review_hash, and base_hash', async () => {
    const api = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('window', { hermesDesktop: { api } })

    await approveSkillProposal(
      'skp_a',
      {
        revision: 3,
        review_hash: reviewHash,
        base_hash: baseHash
      },
      profile
    )

    expect(api).toHaveBeenCalledWith({
      body: {
        revision: 3,
        review_hash: reviewHash,
        base_hash: baseHash
      },
      method: 'POST',
      path: '/api/skills/proposals/skp_a/approve',
      priority: 'foreground',
      profile: 'default'
    })
  })

  it('rejects v2 with a hash and legacy v1 with an empty object', async () => {
    const api = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('window', { hermesDesktop: { api } })

    await rejectSkillProposal('skp_v2', reviewHash, profile)
    await rejectSkillProposal('legacy1', null, profile)

    expect(api).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        body: { review_hash: reviewHash },
        method: 'POST',
        path: '/api/skills/proposals/skp_v2/reject',
        profile: 'default'
      })
    )
    expect(api).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        body: {},
        method: 'POST',
        path: '/api/skills/proposals/legacy1/reject',
        profile: 'default'
      })
    )
  })

  it('requests pending proposals with the capability scope and normalizes the response', async () => {
    const api = vi.fn().mockResolvedValue({
      proposals: [rawProposal()],
      count: 1,
      queue: {
        pending_count: 1,
        max_pending: 25,
        over_limit: false,
        targets_over_limit: 0,
        earliest_expires_at: null,
        broken_count: 0
      }
    })

    vi.stubGlobal('window', { hermesDesktop: { api } })

    const response = await getSkillProposals(profile)

    expect(api).toHaveBeenCalledWith({
      path: '/api/skills/proposals?status=pending',
      priority: 'foreground',
      profile: 'default'
    })
    expect(response.proposals[0].target.skill).toBe('energy-audit-report')
  })
})
