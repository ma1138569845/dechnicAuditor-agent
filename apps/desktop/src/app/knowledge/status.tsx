import { Badge } from '@/components/ui/badge'
import { useI18n } from '@/i18n'

export function ParseStatusBadge({ status }: { status: string }) {
  const { t } = useI18n()
  const k = t.knowledge
  const label =
    status === 'completed'
      ? k.statusCompleted
      : status === 'processing'
        ? k.statusProcessing
        : status === 'failed'
          ? k.statusFailed
          : k.statusPending
  const variant =
    status === 'failed' ? 'destructive' : status === 'processing' ? 'warn' : status === 'completed' ? 'default' : 'muted'

  return (
    <Badge size="xs" variant={variant}>
      {label}
    </Badge>
  )
}

export function ReviewStatusBadge({ status }: { status: string | undefined }) {
  const { t } = useI18n()
  const k = t.knowledge
  const label =
    status === 'approved'
      ? k.reviewApproved
      : status === 'rejected'
        ? k.reviewRejected
        : status === 'pending'
          ? k.reviewPending
          : status || '—'
  const variant: 'default' | 'destructive' | 'muted' | 'warn' =
    status === 'approved' ? 'default' : status === 'rejected' ? 'destructive' : status === 'pending' ? 'warn' : 'muted'

  return (
    <Badge size="xs" variant={variant}>
      {label}
    </Badge>
  )
}

export function JobStatusBadge({ status }: { status: string }) {
  const { t } = useI18n()
  const k = t.knowledge
  const label =
    status === 'completed' || status === 'success'
      ? k.statusCompleted
      : status === 'failed'
        ? k.statusFailed
        : status === 'processing' || status === 'running'
          ? k.statusProcessing
          : k.statusPending
  const variant =
    status === 'failed'
      ? 'destructive'
      : status === 'completed' || status === 'success'
        ? 'default'
        : status === 'processing' || status === 'running'
          ? 'warn'
          : 'muted'

  return (
    <Badge size="xs" variant={variant}>
      {label}
    </Badge>
  )
}
