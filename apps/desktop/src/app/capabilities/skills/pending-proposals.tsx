import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type KeyboardEvent as ReactKeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'

import { approveSkillProposal, getSkillProposal, rejectSkillProposal } from '@/api/skills'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { ErrorState } from '@/components/ui/error-state'
import { Loader } from '@/components/ui/loader'
import type { ProfileScope } from '@/hermes'
import { useI18n } from '@/i18n'
import { invalidateSlashCompletions } from '@/lib/slash-completion-cache'
import { cn } from '@/lib/utils'
import { notify, notifyError } from '@/store/notifications'
import type { SkillProposalDetail, SkillProposalListResponse, SkillProposalQueueState } from '@/types/hermes'

import { DetailColumn, ListColumn, MasterDetail } from '../../master-detail'
import { PanelEmpty } from '../../overlays/panel'

import {
  isSkillProposalApprovable,
  skillProposalDetailQueryKey,
  skillProposalErrorCode,
  skillProposalsQueryKey,
  sortSkillProposals
} from './proposal-data'
import { ProposalDetail } from './proposal-detail'
import { skillsQueryKey } from './skills-data'

interface PendingProposalsProps {
  data?: SkillProposalListResponse
  error: Error | null
  onRetry: () => void
  pending: boolean
  profile: ProfileScope
  onExplicitEdit?: (skill: string) => void
}

type DecisionKind = 'approve' | 'reject'

interface Decision {
  kind: DecisionKind
  proposal: SkillProposalDetail
}

function formatTimestamp(value: null | number): null | string {
  if (!value) {
    return null
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(new Date(value * 1000))
}

function CapacityBanner({ queue }: { queue: SkillProposalQueueState }) {
  const { t } = useI18n()
  const p = t.skills.proposals
  const earliest = formatTimestamp(queue.earliest_expires_at)

  if (
    !queue.over_limit &&
    queue.targets_over_limit.length === 0 &&
    queue.broken_count === 0 &&
    !queue.earliest_expires_at
  ) {
    return null
  }

  return (
    <div
      aria-live="polite"
      className="mx-3 mt-2 rounded-md bg-(--ui-bg-tertiary) px-3 py-2 text-xs text-(--ui-text-secondary)"
    >
      <div className="font-medium text-foreground/85">{p.capacityTitle}</div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
        {queue.over_limit && <span>{p.capacityOver(queue.pending_count, queue.max_pending)}</span>}
        {queue.targets_over_limit.length > 0 && <span>{p.targetCapacityOver(queue.targets_over_limit.length)}</span>}
        {earliest && <span>{p.earliestExpires(earliest)}</span>}
        {queue.broken_count > 0 && <span>{p.brokenRecords(queue.broken_count)}</span>}
      </div>
    </div>
  )
}

function proposalMeta(proposal: SkillProposalDetail | SkillProposalListResponse['proposals'][number]) {
  return {
    conflict: Boolean(proposal.conflict),
    hasWarning: proposal.preview.lint.some(finding => finding.severity.toLowerCase() !== 'error'),
    legacy: proposal.schema_version === 1
  }
}

export function PendingProposals({ data, error, onExplicitEdit, onRetry, pending, profile }: PendingProposalsProps) {
  const { t } = useI18n()
  const p = t.skills.proposals
  const client = useQueryClient()
  const mounted = useRef(true)
  const mutationBusy = useRef(false)
  const detailRoot = useRef<HTMLDivElement>(null)
  const [selectedId, setSelectedId] = useState<null | string>(null)
  const [decision, setDecision] = useState<Decision | null>(null)
  const [decisionBusy, setDecisionBusy] = useState(false)
  const [staleReviews, setStaleReviews] = useState<ReadonlySet<string>>(new Set())
  const proposals = useMemo(() => sortSkillProposals(data?.proposals ?? []), [data?.proposals])

  // eslint-disable-next-line no-restricted-syntax -- lifecycle guard drops stale async completions; it does not mirror an atom
  useEffect(() => {
    mounted.current = true

    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    if (proposals.length === 0) {
      setSelectedId(null)

      return
    }

    if (!selectedId || !proposals.some(proposal => proposal.id === selectedId)) {
      setSelectedId(proposals[0].id)
    }
  }, [proposals, selectedId])

  const detailQuery = useQuery({
    queryKey: skillProposalDetailQueryKey(profile, selectedId ?? ''),
    queryFn: () => getSkillProposal(selectedId!, profile),
    enabled: selectedId !== null,
    retry: false,
    staleTime: 0
  })

  const selected = detailQuery.data?.id === selectedId ? detailQuery.data : null

  function moveSelection(direction: 1 | -1) {
    if (proposals.length === 0) {
      return
    }

    const current = Math.max(
      0,
      proposals.findIndex(proposal => proposal.id === selectedId)
    )

    const next = Math.min(proposals.length - 1, Math.max(0, current + direction))
    setSelectedId(proposals[next].id)
  }

  function handleListKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      moveSelection(1)

      return
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault()
      moveSelection(-1)

      return
    }

    if (event.key === 'Enter') {
      event.preventDefault()
      const primary = detailRoot.current?.querySelector<HTMLButtonElement>('[data-proposal-primary-action="approve"]')

      primary?.focus()
    }
  }

  async function runDecision(action: Decision) {
    if (mutationBusy.current) {
      return
    }

    const proposal = action.proposal
    const listKey = skillProposalsQueryKey(profile, 'pending')
    const detailKey = skillProposalDetailQueryKey(profile, proposal.id)
    const previous = client.getQueryData<SkillProposalListResponse>(listKey)
    mutationBusy.current = true
    setDecisionBusy(true)

    client.setQueryData<SkillProposalListResponse>(listKey, current =>
      current
        ? {
            ...current,
            proposals: current.proposals.filter(row => row.id !== proposal.id),
            count: Math.max(0, current.count - 1),
            queue: {
              ...current.queue,
              pending_count: Math.max(0, current.queue.pending_count - 1)
            }
          }
        : current
    )

    try {
      if (action.kind === 'approve') {
        if (!isSkillProposalApprovable(proposal) || !proposal.review_hash || !proposal.base_hash) {
          throw new Error(p.approveFailed)
        }

        await approveSkillProposal(
          proposal.id,
          {
            revision: proposal.revision,
            review_hash: proposal.review_hash,
            base_hash: proposal.base_hash
          },
          profile
        )
        client.removeQueries({ queryKey: detailKey, exact: true })

        if (mounted.current) {
          notify({ kind: 'success', title: p.approved, message: '' })
        }
      } else {
        await rejectSkillProposal(proposal.id, proposal.review_hash, profile)
        client.removeQueries({ queryKey: detailKey, exact: true })

        if (mounted.current) {
          notify({ kind: 'success', title: p.rejected, message: '' })
        }
      }
    } catch (error) {
      client.setQueryData(listKey, previous)

      const staleReview =
        action.kind === 'approve' &&
        ['review_hash_mismatch', 'review_refresh_required'].includes(skillProposalErrorCode(error) ?? '')

      if (staleReview && mounted.current) {
        setStaleReviews(current => new Set(current).add(proposal.id))
      }

      if (mounted.current) {
        notifyError(error, action.kind === 'approve' ? p.approveFailed : p.rejectFailed)
      }

      if (staleReview) {
        return
      }

      throw error
    } finally {
      mutationBusy.current = false

      if (mounted.current) {
        setDecisionBusy(false)
      }

      await client.invalidateQueries({ queryKey: detailKey, exact: true })
      await client.invalidateQueries({ queryKey: listKey, exact: true })
      await client.invalidateQueries({ queryKey: skillsQueryKey(profile), exact: true })
      invalidateSlashCompletions()
    }
  }

  if (pending && !data) {
    return <Loader className="mx-auto my-10 size-7 text-(--ui-text-tertiary)" label={p.loading} type="rose-curve" />
  }

  if (error && !data) {
    return (
      <div className="grid h-full place-items-center p-6">
        <ErrorState description={error.message} title={p.loadFailed}>
          <Button onClick={onRetry} size="sm" variant="secondary">
            {p.retry}
          </Button>
        </ErrorState>
      </div>
    )
  }

  if (!data || proposals.length === 0) {
    return <PanelEmpty description={p.emptyDescription} icon="inbox" title={p.emptyTitle} />
  }

  const queue = data.queue

  return (
    <div className="flex h-full min-h-0 flex-col">
      <CapacityBanner queue={queue} />
      <div className="min-h-0 flex-1">
        <MasterDetail split="wide">
          <ListColumn
            header={
              <div className="mb-1 flex h-7 items-center justify-between gap-2 px-2">
                <span className="text-xs font-medium text-foreground">{p.title}</span>
                <Badge size="xs" variant="muted">
                  {queue.pending_count}
                </Badge>
              </div>
            }
          >
            <div
              aria-label={p.queueLabel}
              className="space-y-0.5"
              onKeyDown={handleListKeyDown}
              role="listbox"
              tabIndex={0}
            >
              {proposals.map(proposal => {
                const meta = proposalMeta(proposal)
                const active = proposal.id === selectedId

                return (
                  <button
                    aria-selected={active}
                    className={cn(
                      'flex w-full cursor-pointer flex-col gap-1 rounded-md px-2 py-2 text-left transition-colors hover:transition-none',
                      active
                        ? 'bg-(--ui-row-active-background) text-foreground'
                        : 'text-(--ui-text-secondary) hover:bg-(--ui-control-active-background) hover:text-foreground'
                    )}
                    key={proposal.id}
                    onClick={() => setSelectedId(proposal.id)}
                    role="option"
                    type="button"
                  >
                    <span className="flex min-w-0 w-full items-center gap-2">
                      <span className="min-w-0 flex-1 truncate text-[0.78rem] font-medium">
                        {proposal.target.skill}
                      </span>
                      <Badge size="xs" variant="outline">
                        {p.actionLabel(proposal.operation.action)}
                      </Badge>
                    </span>
                    <span className="flex min-w-0 w-full items-center gap-1.5 text-[0.62rem] text-muted-foreground">
                      <span>{p.evidence(proposal.evidence_count)}</span>
                      {meta.conflict && (
                        <Badge size="xs" variant="destructive">
                          {p.targetChanged}
                        </Badge>
                      )}
                      {meta.hasWarning && (
                        <Badge size="xs" variant="warn">
                          !
                        </Badge>
                      )}
                      {meta.legacy && (
                        <Badge size="xs" variant="muted">
                          {p.legacyPending}
                        </Badge>
                      )}
                    </span>
                  </button>
                )
              })}
            </div>
          </ListColumn>

          <div className="min-h-0" ref={detailRoot}>
            <DetailColumn>
              {!selectedId ? (
                <PanelEmpty description={p.noSelectionDescription} icon="inspect" title={p.noSelectionTitle} />
              ) : detailQuery.error ? (
                <ErrorState description={detailQuery.error.message} title={p.detailLoadFailed}>
                  <Button onClick={() => void detailQuery.refetch()} size="sm" variant="secondary">
                    {p.retry}
                  </Button>
                </ErrorState>
              ) : !selected ? (
                <Loader
                  className="mx-auto my-10 size-6 text-(--ui-text-tertiary)"
                  label={p.loading}
                  type="rose-curve"
                />
              ) : (
                <ProposalDetail
                  busy={decisionBusy}
                  onApprove={() => setDecision({ kind: 'approve', proposal: selected })}
                  onExplicitEdit={() => onExplicitEdit?.(selected.target.skill)}
                  onReject={() => setDecision({ kind: 'reject', proposal: selected })}
                  proposal={selected}
                  reviewStale={staleReviews.has(selected.id)}
                />
              )}
            </DetailColumn>
          </div>
        </MasterDetail>
      </div>

      <ConfirmDialog
        busyLabel={decision?.kind === 'approve' ? p.approve : p.reject}
        confirmLabel={decision?.kind === 'approve' ? p.approve : p.reject}
        description={
          decision?.kind === 'approve' ? p.confirmApproveBody(decision.proposal.revision) : p.confirmRejectBody
        }
        destructive={decision?.kind === 'reject'}
        onClose={() => {
          if (!decisionBusy) {
            setDecision(null)
          }
        }}
        onConfirm={() => (decision ? runDecision(decision) : undefined)}
        open={decision !== null}
        title={
          decision
            ? decision.kind === 'approve'
              ? p.confirmApproveTitle(decision.proposal.target.skill)
              : p.confirmRejectTitle(decision.proposal.target.skill)
            : ''
        }
      />
    </div>
  )
}
