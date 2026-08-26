import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { listCurationJobs, listVectorizationJobs } from '@/api/knowledge'
import { PageLoader } from '@/components/page-loader'
import { Badge } from '@/components/ui/badge'
import { useI18n } from '@/i18n'

import { PanelEmpty } from '../overlays/panel'

import { formatKbDateTime, isActiveJobStatus } from './format'
import { knowledgeKeys } from './keys'
import { JobStatusBadge } from './status'

export function JobsTab({ kbId }: { kbId: string }) {
  const { t } = useI18n()
  const k = t.knowledge
  const vectorQuery = useQuery({
    queryFn: () => listVectorizationJobs(kbId),
    queryKey: knowledgeKeys.vectorJobs(kbId),
    refetchInterval: query => {
      const jobs = query.state.data?.jobs ?? []

      return jobs.some(job => isActiveJobStatus(job.status)) ? 2_500 : false
    }
  })
  const curationQuery = useQuery({
    queryFn: () => listCurationJobs(kbId),
    queryKey: knowledgeKeys.curationJobs(kbId),
    refetchInterval: query => {
      const jobs = query.state.data?.jobs ?? []

      return jobs.some(job => isActiveJobStatus(job.status)) ? 2_500 : false
    }
  })

  const rows = useMemo(() => {
    const vector = (vectorQuery.data?.jobs ?? []).map(job => ({
      created_at: job.created_at,
      detail: job.error || `${Math.round(Number(job.progress) || 0)}%`,
      id: job.id,
      kind: k.jobTypeVectorize,
      status: job.status
    }))
    const curation = (curationQuery.data?.jobs ?? []).map(job => ({
      created_at: job.created_at,
      detail: job.error_message || '',
      id: job.id,
      kind: job.job_type || k.jobTypeCurate,
      status: job.status
    }))

    return [...vector, ...curation].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
  }, [curationQuery.data, k.jobTypeCurate, k.jobTypeVectorize, vectorQuery.data])

  if ((vectorQuery.isPending && !vectorQuery.data) || (curationQuery.isPending && !curationQuery.data)) {
    return <PageLoader label={t.common.loading} />
  }

  if (rows.length === 0) {
    return <PanelEmpty description={k.noJobsDesc} icon="history" title={k.noJobsTitle} />
  }

  return (
    <ul className="flex h-full min-h-0 flex-col overflow-y-auto px-6 pb-6">
      {rows.map(row => (
        <li
          className="flex flex-wrap items-center gap-2 border-t border-(--ui-stroke-tertiary) py-3 first:border-t-0"
          key={row.id}
        >
          <Badge size="xs" variant="outline">
            {row.kind}
          </Badge>
          <JobStatusBadge status={row.status} />
          {row.detail ? <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{row.detail}</span> : null}
          <time className="shrink-0 text-[0.65rem] text-muted-foreground">{formatKbDateTime(row.created_at)}</time>
        </li>
      ))}
    </ul>
  )
}
