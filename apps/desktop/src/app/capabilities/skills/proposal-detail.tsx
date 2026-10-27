import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorBanner } from '@/components/ui/error-state'
import { useI18n } from '@/i18n'
import { AlertTriangle, CheckCircle2, Clock, FileText, ShieldLock } from '@/lib/icons'
import type { SkillProposalDetail } from '@/types/hermes'

import { isSkillProposalApprovable } from './proposal-data'

interface ProposalDetailProps {
  busy: boolean
  onApprove: () => void
  onExplicitEdit: () => void
  onReject: () => void
  proposal: SkillProposalDetail
  reviewStale: boolean
}

function formatTimestamp(value: number): string {
  if (!value) {
    return '—'
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(new Date(value * 1000))
}

function diffKind(line: string): '-' | '+' | ' ' {
  return line.startsWith('+') ? '+' : line.startsWith('-') ? '-' : ' '
}

export function ProposalDetail({
  busy,
  onApprove,
  onExplicitEdit,
  onReject,
  proposal,
  reviewStale
}: ProposalDetailProps) {
  const { t } = useI18n()
  const p = t.skills.proposals
  const approvable = isSkillProposalApprovable(proposal)

  const lintErrors = proposal.preview.lint.filter(finding =>
    ['critical', 'error', 'high'].includes(finding.severity.toLowerCase())
  )

  const lintWarnings = proposal.preview.lint.filter(finding => !lintErrors.includes(finding))
  const security = proposal.preview.security

  const securityBlocked =
    !security || ['blocked', 'dangerous', 'error', 'unavailable', 'unknown'].includes(security.verdict.toLowerCase())

  const legacy = proposal.schema_version === 1
  const expired = proposal.status === 'expired'
  const changed = Boolean(proposal.conflict)

  const notices = legacy
    ? [p.legacyPendingBody]
    : [
        ...(expired ? [p.expiredDescription] : []),
        ...(changed ? [p.targetChangedHelp] : []),
        ...(securityBlocked ? [p.securityUnavailable] : []),
        ...(lintErrors.length ? [p.lintErrors(lintErrors.length)] : [])
      ]

  return (
    <article className="space-y-5 pb-3" data-proposal-detail>
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={legacy ? 'warn' : 'default'}>{p.actionLabel(proposal.operation.action)}</Badge>
          <span className="font-mono text-sm font-medium text-foreground">{proposal.target.skill}</span>
          {proposal.operation.file_path && (
            <span className="text-xs text-muted-foreground">{proposal.operation.file_path}</span>
          )}
          <Badge variant="outline">{p.revision(proposal.revision)}</Badge>
          {legacy && <Badge variant="warn">{p.legacyPending}</Badge>}
          {expired && <Badge variant="muted">{p.expired}</Badge>}
          {changed && <Badge variant="destructive">{p.targetChanged}</Badge>}
        </div>
        <p className="text-sm leading-6 text-foreground/90">{proposal.preview.summary}</p>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[0.68rem] text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Clock className="size-3" />
            {p.createdAt(formatTimestamp(proposal.created_at))}
          </span>
          <span className="inline-flex items-center gap-1">
            <Clock className="size-3" />
            {p.lastSeenAt(formatTimestamp(proposal.last_seen_at))}
          </span>
          <span className="inline-flex items-center gap-1">
            <Clock className="size-3" />
            {p.expiresAt(formatTimestamp(proposal.expires_at))}
          </span>
        </div>
      </header>

      {reviewStale && <ErrorBanner>{p.reviewRefreshRequired}</ErrorBanner>}
      {notices.map((notice, index) => (
        <div
          className="flex items-start gap-2 rounded-md bg-(--ui-bg-tertiary) px-3 py-2 text-xs text-(--ui-text-secondary)"
          key={`${notice}-${index}`}
        >
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-600 dark:text-amber-300" />
          <span>{notice}</span>
        </div>
      ))}

      <section aria-labelledby="proposal-evidence-title" className="space-y-2">
        <h3 className="text-xs font-medium text-foreground" id="proposal-evidence-title">
          {p.evidence(proposal.evidence.length)}
        </h3>
        <div className="space-y-2">
          {proposal.evidence.map((evidence, index) => (
            <div className="flex items-start gap-2 text-xs leading-5" key={`${evidence.kind}-${index}`}>
              <CheckCircle2 className="mt-1 size-3.5 shrink-0 text-emerald-600 dark:text-emerald-300" />
              <div className="min-w-0">
                <div className="font-medium text-foreground/85">{p.evidenceKind[evidence.kind]}</div>
                <div className="break-words text-muted-foreground">{evidence.reason}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {proposal.preview.diff && (
        <section aria-labelledby="proposal-diff-title" className="space-y-2">
          <div className="flex items-center gap-2">
            <FileText className="size-3.5 text-muted-foreground" />
            <h3 className="text-xs font-medium text-foreground" id="proposal-diff-title">
              {p.diff}
            </h3>
          </div>
          <pre className="max-h-80 overflow-auto rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-tertiary) py-2 font-mono text-[0.68rem] leading-5">
            {proposal.preview.diff.split('\n').map((line, index) => {
              const kind = diffKind(line)

              return (
                <span
                  aria-label={p.diffLine(kind, index + 1)}
                  className={
                    kind === '+'
                      ? 'block bg-emerald-500/10 px-3 text-emerald-700 dark:text-emerald-300'
                      : kind === '-'
                        ? 'block bg-destructive/10 px-3 text-destructive'
                        : 'block px-3 text-muted-foreground'
                  }
                  key={`${index}-${line}`}
                >
                  {line || ' '}
                </span>
              )
            })}
          </pre>
        </section>
      )}

      <section aria-labelledby="proposal-validation-title" className="space-y-2">
        <div className="flex items-center gap-2">
          <ShieldLock className="size-3.5 text-muted-foreground" />
          <h3 className="text-xs font-medium text-foreground" id="proposal-validation-title">
            {security ? p.securityVerdict(security.verdict) : p.securityUnavailable}
          </h3>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {security && !securityBlocked && (
            <Badge variant="success">
              <CheckCircle2 />
              {p.securitySafe}
            </Badge>
          )}
          {lintErrors.length > 0 && <Badge variant="destructive">{p.lintErrors(lintErrors.length)}</Badge>}
          {lintWarnings.length > 0 && <Badge variant="warn">{p.lintWarnings(lintWarnings.length)}</Badge>}
          {proposal.related?.possible_duplicates.map(duplicate => (
            <Badge key={duplicate.id} variant="outline">
              {p.possibleDuplicate(duplicate.id)}
            </Badge>
          ))}
        </div>
        {(lintErrors.length > 0 || lintWarnings.length > 0) && (
          <ul className="space-y-1 text-xs text-muted-foreground">
            {[...lintErrors, ...lintWarnings].map((finding, index) => (
              <li className="flex gap-2" key={`${finding.rule ?? finding.severity}-${index}`}>
                <Badge size="xs" variant={lintErrors.includes(finding) ? 'destructive' : 'warn'}>
                  {finding.severity}
                </Badge>
                <span>{finding.message || finding.rule || finding.severity}</span>
              </li>
            ))}
          </ul>
        )}
        {security?.findings.length ? (
          <ul className="space-y-1 text-xs text-muted-foreground">
            {security.findings.map((finding, index) => (
              <li className="break-words" key={index}>
                {String(finding.message || finding.description || finding.rule || JSON.stringify(finding))}
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="space-y-1 rounded-md bg-(--ui-bg-tertiary) px-3 py-2 font-mono text-[0.62rem] text-muted-foreground">
        <div className="break-all">
          <span className="text-foreground/70">{p.reviewHash}: </span>
          {proposal.review_hash ?? '—'}
        </div>
        <div className="break-all">
          <span className="text-foreground/70">{p.baseHash}: </span>
          {proposal.base_hash ?? '—'}
        </div>
      </section>

      <footer className="flex flex-wrap items-center justify-end gap-2 pt-1">
        {legacy && (
          <Button onClick={onExplicitEdit} size="sm" variant="secondary">
            {p.reviewAsExplicitEdit}
          </Button>
        )}
        <Button disabled={busy} onClick={onReject} size="sm" variant="secondary">
          {p.reject}
        </Button>
        <Button data-proposal-primary-action="approve" disabled={busy || !approvable} onClick={onApprove} size="sm">
          {p.approve}
        </Button>
      </footer>
    </article>
  )
}
