import { type ProfileScope, profileScopeKey } from '@/api/client'
import type {
  SkillProposalDetail,
  SkillProposalEvidence,
  SkillProposalListResponse,
  SkillProposalQueueState,
  SkillProposalStatus,
  SkillProposalSummary
} from '@/types/hermes'

type RecordValue = Record<string, unknown>

const BLOCKING_SECURITY_VERDICTS = new Set(['blocked', 'dangerous', 'error', 'unavailable', 'unknown'])
const BLOCKING_FINDING_LEVELS = new Set(['critical', 'error', 'high'])

function isRecord(value: unknown): value is RecordValue {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function asRecord(value: unknown): RecordValue {
  return isRecord(value) ? value : {}
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function targetInfo(record: RecordValue): { fallback: string; names: string[] } {
  const target = asRecord(record.target)
  const operation = asRecord(record.operation)
  const payload = asRecord(record.payload)
  const name = asString(target.name) || asString(operation.name) || asString(payload.name)

  const names = Array.isArray(target.names)
    ? target.names.filter((value): value is string => typeof value === 'string')
    : []

  return { fallback: name || names[0] || asString(record.id), names }
}

function proposalStatus(value: unknown): SkillProposalStatus {
  return value === 'claiming' || value === 'applied' || value === 'rejected' || value === 'expired' ? value : 'pending'
}

function operationOf(record: RecordValue, target: string): SkillProposalSummary['operation'] {
  const operation = asRecord(record.operation)
  const payload = asRecord(record.payload)
  const filePath = asString(operation.file_path) || asString(record.file_path)
  const action = asString(operation.action) || asString(record.action) || asString(payload.action) || 'write'

  return {
    action,
    ...(filePath ? { file_path: filePath } : {}),
    ...(target ? { name: target } : {})
  }
}

function prefixedLines(prefix: string, value: string): string[] {
  return value.split('\n').map(line => `${prefix}${line}`)
}

function patchDiff(operation: RecordValue, fallbackTarget: string): string | undefined {
  const explicitDiff = asString(operation.patch) || asString(operation.diff)

  if (explicitDiff) {
    return explicitDiff
  }

  const hasOldString = typeof operation.old_string === 'string'
  const hasNewString = typeof operation.new_string === 'string'

  if (!hasOldString && !hasNewString) {
    return undefined
  }

  const target = asString(operation.name) || fallbackTarget
  const filePath = asString(operation.file_path) || 'SKILL.md'
  const label = `${target}/${filePath}`
  const oldLines = hasOldString ? prefixedLines('-', asString(operation.old_string)) : []
  const newLines = hasNewString ? prefixedLines('+', asString(operation.new_string)) : []

  return [`--- ${label}`, `+++ ${label}`, ...oldLines, ...newLines].join('\n')
}

function operationDiff(operation: RecordValue, fallbackTarget: string): string | undefined {
  const explicitDiff = asString(operation.patch) || asString(operation.diff)

  if (explicitDiff) {
    return explicitDiff
  }

  if (operation.action === 'batch') {
    const operations = Array.isArray(operation.operations) ? operation.operations : []

    const diffs = operations
      .filter(isRecord)
      .map(item => patchDiff(item, fallbackTarget))
      .filter((diff): diff is string => Boolean(diff))

    return diffs.length > 0 ? diffs.join('\n') : undefined
  }

  return patchDiff(operation, fallbackTarget)
}

function fallbackDiff(record: RecordValue, operation: RecordValue): string | undefined {
  const preview = asRecord(record.preview)
  const previewDiff = asString(preview.diff)

  if (previewDiff) {
    return previewDiff
  }

  const derivedDiff = operationDiff(operation, asString(asRecord(record.target).name))

  if (derivedDiff) {
    return derivedDiff
  }

  const payload = asRecord(record.payload)
  const content = asString(operation.content) || asString(payload.content)

  if (!content) {
    const filePath = asString(operation.file_path) || asString(record.file_path)

    return filePath ? `  ${filePath}` : undefined
  }

  const action = asString(operation.action) || asString(record.action) || asString(payload.action)
  const prefix = action === 'create' || action === 'write_file' ? '+' : ' '

  return content
    .split('\n')
    .map(line => `${prefix}${line}`)
    .join('\n')
}

function lintOf(record: RecordValue): SkillProposalSummary['preview']['lint'] {
  const preview = asRecord(record.preview)
  const rows = Array.isArray(record.lint) ? record.lint : Array.isArray(preview.lint) ? preview.lint : []

  return rows.filter(isRecord).map(row => ({
    severity: asString(row.severity) || 'warning',
    ...(asString(row.message) ? { message: asString(row.message) } : {}),
    ...(asString(row.rule) ? { rule: asString(row.rule) } : {})
  }))
}

function securityOf(record: RecordValue): SkillProposalSummary['preview']['security'] {
  const preview = asRecord(record.preview)
  const raw = isRecord(record.security) ? record.security : isRecord(preview.security) ? preview.security : null

  if (!raw) {
    return undefined
  }

  return {
    verdict: asString(raw.verdict) || 'unknown',
    findings: Array.isArray(raw.findings) ? raw.findings.filter(isRecord) : []
  }
}

function evidenceOf(record: RecordValue): SkillProposalEvidence[] {
  const rows = Array.isArray(record.evidence) ? record.evidence : []

  return rows.filter(isRecord).map(row => {
    const kind = row.kind

    return {
      kind:
        kind === 'user_request' ||
        kind === 'user_correction' ||
        kind === 'skill_incomplete' ||
        kind === 'repeated_class'
          ? kind
          : 'user_request',
      message_refs: Array.isArray(row.message_refs)
        ? row.message_refs.filter((value): value is number => typeof value === 'number')
        : [],
      reason: asString(row.reason)
    }
  })
}

function relatedOf(record: RecordValue): SkillProposalSummary['related'] {
  const related = asRecord(record.related)
  const duplicates = Array.isArray(related.possible_duplicates) ? related.possible_duplicates : []

  const possible_duplicates = duplicates
    .filter(isRecord)
    .map(row => ({ id: asString(row.id), reason: asString(row.reason) }))
    .filter(row => row.id)

  if (possible_duplicates.length === 0 && related.overlap_count === undefined) {
    return undefined
  }

  return {
    possible_duplicates,
    overlap_count: asNumber(related.overlap_count, possible_duplicates.length)
  }
}

export function normalizeSkillProposalSummary(value: unknown): SkillProposalSummary {
  if (!isRecord(value)) {
    throw new Error('Skill proposal response is not an object')
  }

  const id = asString(value.id)

  if (!id) {
    throw new Error('Skill proposal response is missing id')
  }

  const schemaVersion = value.schema_version === 2 ? 2 : 1
  const reviewHash = asString(value.review_hash)
  const baseHash = asString(value.base_hash)

  if (schemaVersion === 2 && !reviewHash) {
    throw new Error(`Skill proposal ${id} is missing review_hash`)
  }

  if (schemaVersion === 2 && !baseHash) {
    throw new Error(`Skill proposal ${id} is missing base_hash`)
  }

  const target = targetInfo(value)
  const operation = operationOf(value, target.fallback)
  const previewRecord = asRecord(value.preview)
  const lint = lintOf(value)
  const rawSummary = asString(previewRecord.summary)

  const summary =
    rawSummary ||
    `${operation.action} ${target.fallback}${operation.file_path ? ` / ${operation.file_path}` : ''}`.trim()

  const diff = fallbackDiff(value, asRecord(value.operation))
  const security = securityOf(value)
  const related = relatedOf(value)
  const conflict = asString(value.conflict)

  return {
    schema_version: schemaVersion,
    id,
    status: proposalStatus(value.status),
    revision: Math.max(1, Math.floor(asNumber(value.revision, 1))),
    review_hash: schemaVersion === 2 ? reviewHash : null,
    base_hash: schemaVersion === 2 ? baseHash : null,
    created_at: asNumber(value.created_at),
    last_seen_at: asNumber(value.last_seen_at, asNumber(value.updated_at, asNumber(value.created_at))),
    expires_at: asNumber(value.expires_at),
    evidence_count: Array.isArray(value.evidence) ? value.evidence.length : 0,
    target: {
      skill: target.fallback,
      ...(target.names.length > 1 ? { names: target.names } : {})
    },
    operation,
    preview: {
      summary,
      ...(diff ? { diff } : {}),
      lint,
      ...(security ? { security } : {})
    },
    conflict: conflict || null,
    ...(schemaVersion === 1 ? { legacy_reason: 'legacy_pending_requires_explicit_edit' as const } : {}),
    ...(related ? { related } : {})
  }
}

export function normalizeSkillProposalDetail(value: unknown): SkillProposalDetail {
  if (!isRecord(value)) {
    throw new Error('Skill proposal response is not an object')
  }

  return {
    ...normalizeSkillProposalSummary(value),
    evidence: evidenceOf(value)
  }
}

function targetsOverLimit(value: unknown, maxPending: number): SkillProposalQueueState['targets_over_limit'] {
  if (Array.isArray(value)) {
    return value.filter(isRecord).map(row => ({
      target: asString(row.target),
      pending_count: asNumber(row.pending_count),
      max_pending: asNumber(row.max_pending, maxPending)
    }))
  }

  // The Phase B backend currently returns a count, not per-target rows. Preserve
  // that count in the typed model without inventing target names or counts.
  return Array.from({ length: Math.max(0, Math.floor(asNumber(value))) }, () => ({
    target: '',
    pending_count: 0,
    max_pending: maxPending
  }))
}

function normalizeQueue(value: unknown): SkillProposalQueueState {
  const queue = asRecord(value)
  const maxPending = Math.max(0, Math.floor(asNumber(queue.max_pending, 25)))

  return {
    pending_count: Math.max(0, Math.floor(asNumber(queue.pending_count))),
    max_pending: maxPending,
    over_limit: queue.over_limit === true,
    targets_over_limit: targetsOverLimit(queue.targets_over_limit, maxPending),
    earliest_expires_at:
      typeof queue.earliest_expires_at === 'number' && Number.isFinite(queue.earliest_expires_at)
        ? queue.earliest_expires_at
        : null,
    broken_count: Math.max(0, Math.floor(asNumber(queue.broken_count)))
  }
}

export function normalizeSkillProposalList(value: unknown): SkillProposalListResponse {
  if (!isRecord(value) || !Array.isArray(value.proposals)) {
    throw new Error('Skill proposal list response is invalid')
  }

  const proposals = value.proposals.map(normalizeSkillProposalSummary)
  const count = asNumber(value.count, -1)

  if (count !== proposals.length) {
    throw new Error(`Skill proposal count ${count} does not match ${proposals.length} records`)
  }

  return {
    proposals,
    count,
    queue: normalizeQueue(value.queue)
  }
}

function lintRisk(proposal: SkillProposalSummary): number {
  return proposal.preview.lint.reduce(
    (risk, finding) => {
      const severity = finding.severity.toLowerCase()

      return severity === 'error' || severity === 'critical' || severity === 'high'
        ? Math.max(risk, 3)
        : Math.max(risk, 1)
    },
    BLOCKING_SECURITY_VERDICTS.has(proposal.preview.security?.verdict.toLowerCase() ?? '') ? 3 : 0
  )
}

export function sortSkillProposals(proposals: SkillProposalSummary[]): SkillProposalSummary[] {
  return [...proposals].sort((left, right) => {
    const leftRank = left.conflict ? 4 : lintRisk(left)
    const rightRank = right.conflict ? 4 : lintRisk(right)

    if (leftRank !== rightRank) {
      return rightRank - leftRank
    }

    if (left.last_seen_at !== right.last_seen_at) {
      return right.last_seen_at - left.last_seen_at
    }

    const target = left.target.skill.localeCompare(right.target.skill)

    return target || left.id.localeCompare(right.id)
  })
}

export function isSkillProposalApprovable(proposal: SkillProposalSummary): boolean {
  if (
    proposal.schema_version !== 2 ||
    proposal.status !== 'pending' ||
    !proposal.review_hash ||
    !proposal.base_hash ||
    proposal.conflict
  ) {
    return false
  }

  if (proposal.preview.lint.some(finding => BLOCKING_FINDING_LEVELS.has(finding.severity.toLowerCase()))) {
    return false
  }

  const security = proposal.preview.security

  if (!security || BLOCKING_SECURITY_VERDICTS.has(security.verdict.toLowerCase())) {
    return false
  }

  return !security.findings.some(finding => {
    const severity = asString(finding.severity).toLowerCase()

    return BLOCKING_FINDING_LEVELS.has(severity)
  })
}

export function skillProposalErrorCode(error: unknown): null | string {
  const message = error instanceof Error ? error.message : String(error)
  const match = /"error"\s*:\s*"([^"]+)"/.exec(message) ?? /\berror=([a-z_]+)\b/.exec(message)

  return match?.[1] ?? null
}

export function skillProposalsQueryKey(profile: ProfileScope, status = 'pending') {
  return ['skill-proposals', profileScopeKey(profile), status] as const
}

export function skillProposalDetailQueryKey(profile: ProfileScope, id: string) {
  return ['skill-proposal', profileScopeKey(profile), id] as const
}
