import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'

import {
  generateFolderWiki,
  getKnowledgeBase,
  getKnowledgeStats,
  listCurationJobs,
  listVectorizationJobs,
  rebuildKnowledgeBase,
  startBulkWiki,
  startCuration,
  startHierarchicalWiki
} from '@/api/knowledge'
import { PageLoader } from '@/components/page-loader'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { useI18n } from '@/i18n'
import { ChevronDown, ChevronLeft } from '@/lib/icons'
import { queryClient } from '@/lib/query-client'
import { notify, notifyError } from '@/store/notifications'

import { useRefreshHotkey } from '../hooks/use-refresh-hotkey'
import { useRouteEnumParam } from '../hooks/use-route-enum-param'
import { PanelEmpty } from '../overlays/panel'
import { PageSearchShell } from '../page-search-shell'
import { KNOWLEDGE_ROUTE } from '../routes'

import { DocumentsTab } from './documents'
import { formatBytes, isActiveJobStatus } from './format'
import { GraphTab } from './graph'
import { JobsTab } from './jobs'
import { knowledgeKeys } from './keys'
import { KnowledgeList } from './list'
import { KnowledgeLlmConfirm } from './llm-confirm'
import { SearchTab } from './search'
import { WikiTab } from './wiki'

export function KnowledgeView() {
  const { kbId } = useParams()

  return kbId ? <KnowledgeDetail /> : <KnowledgeList />
}

const TABS = ['documents', 'search', 'wiki', 'graph', 'jobs', 'stats'] as const

type KnowledgeTab = (typeof TABS)[number]
type GenerateAction = 'bulk-wiki' | 'curate' | 'folder-wiki' | 'hierarchical'

export function KnowledgeDetail() {
  const { kbId = '' } = useParams()
  const { t } = useI18n()
  const k = t.knowledge
  const navigate = useNavigate()
  const [tab, setTab] = useRouteEnumParam('tab', TABS, 'documents')
  const [folderId, setFolderId] = useState<null | string>(null)
  const [docQuery, setDocQuery] = useState('')
  const [page, setPage] = useState(1)
  const [generateAction, setGenerateAction] = useState<GenerateAction | null>(null)
  const [rebuildOpen, setRebuildOpen] = useState(false)
  const [generateBusy, setGenerateBusy] = useState(false)
  const prevJobsActive = useRef(false)

  const kbQuery = useQuery({
    enabled: Boolean(kbId),
    queryFn: () => getKnowledgeBase(kbId),
    queryKey: knowledgeKeys.base(kbId)
  })

  const statsQuery = useQuery({
    enabled: Boolean(kbId),
    queryFn: () => getKnowledgeStats(kbId),
    queryKey: knowledgeKeys.stats(kbId)
  })

  const vectorJobsQuery = useQuery({
    enabled: Boolean(kbId),
    queryFn: () => listVectorizationJobs(kbId),
    queryKey: knowledgeKeys.vectorJobs(kbId),
    refetchInterval: query => {
      const jobs = query.state.data?.jobs ?? []

      return jobs.some(job => isActiveJobStatus(job.status)) ? 2_500 : false
    }
  })

  const curationJobsQuery = useQuery({
    enabled: Boolean(kbId),
    queryFn: () => listCurationJobs(kbId),
    queryKey: knowledgeKeys.curationJobs(kbId),
    refetchInterval: query => {
      const jobs = query.state.data?.jobs ?? []

      return jobs.some(job => isActiveJobStatus(job.status)) ? 2_500 : false
    }
  })

  const jobsActive =
    (vectorJobsQuery.data?.jobs ?? []).some(job => isActiveJobStatus(job.status)) ||
    (curationJobsQuery.data?.jobs ?? []).some(job => isActiveJobStatus(job.status))

  useEffect(() => {
    if (prevJobsActive.current && !jobsActive) {
      void queryClient.invalidateQueries({ queryKey: knowledgeKeys.all })
    }

    prevJobsActive.current = jobsActive
  }, [jobsActive])

  useRefreshHotkey(() => {
    void queryClient.invalidateQueries({ queryKey: knowledgeKeys.all })
  })

  if (!kbId) {
    return null
  }

  if (kbQuery.isPending && !kbQuery.data) {
    return <PageLoader label={t.common.loading} />
  }

  if (kbQuery.error || !kbQuery.data) {
    return (
      <PanelEmpty
        action={
          <Button onClick={() => navigate(KNOWLEDGE_ROUTE)} size="sm" variant="secondary">
            {k.backToList}
          </Button>
        }
        description={kbQuery.error instanceof Error ? kbQuery.error.message : k.notFound}
        icon="warning"
        title={k.notFound}
      />
    )
  }

  const kb = kbQuery.data
  const stats = statsQuery.data ?? kb.stats
  const searchHidden = tab !== 'documents'
  const tabs = [
    { id: 'documents', label: k.tabDocuments },
    { id: 'search', label: k.tabSearch },
    { id: 'wiki', label: k.tabWiki },
    { id: 'graph', label: k.tabGraph },
    { id: 'jobs', label: k.tabJobs },
    { id: 'stats', label: k.tabStats }
  ]

  async function runGenerate(action: GenerateAction) {
    setGenerateBusy(true)

    try {
      if (action === 'folder-wiki') {
        await generateFolderWiki(kbId, folderId, { curate: false })
      } else if (action === 'bulk-wiki') {
        await startBulkWiki(kbId, { folderId })
      } else if (action === 'hierarchical') {
        await startHierarchicalWiki(kbId, { folderId })
      } else {
        await startCuration(kbId, { folderId, reviewStatus: 'approved' })
      }

      await queryClient.invalidateQueries({ queryKey: knowledgeKeys.all })
      notify({ kind: 'success', message: k.actionStarted })
      setTab(action === 'curate' || action === 'bulk-wiki' ? 'jobs' : 'wiki')
    } catch (err) {
      notifyError(err, k.actionFailed)
      throw err
    } finally {
      setGenerateBusy(false)
    }
  }

  return (
    <PageSearchShell
      activeTab={tab}
      onSearchChange={value => {
        setDocQuery(value)
        setPage(1)
      }}
      onTabChange={id => setTab(id as KnowledgeTab)}
      searchHidden={searchHidden}
      searchPlaceholder={k.filterDocuments}
      searchTrailingAction={
        <Button onClick={() => navigate(KNOWLEDGE_ROUTE)} size="sm" variant="ghost">
          <ChevronLeft />
          {k.backToList}
        </Button>
      }
      searchValue={docQuery}
      tabs={tabs}
    >
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex shrink-0 items-start justify-between gap-3 px-6 pb-2">
          <div className="min-w-0">
            <h1 className="truncate text-base font-medium text-foreground">{kb.name}</h1>
            {kb.description ? (
              <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{kb.description}</p>
            ) : null}
            {stats ? (
              <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[0.65rem] text-muted-foreground">
                <span>
                  {stats.total_documents} {k.statsTotal}
                </span>
                <span>
                  {stats.completed} {k.statsCompleted}
                </span>
                <span>
                  {stats.processing} {k.statsProcessing}
                </span>
                {stats.failed ? (
                  <span>
                    {stats.failed} {k.statsFailed}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button disabled={generateBusy} size="sm" variant="secondary">
                  {k.generate}
                  <ChevronDown />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setGenerateAction('folder-wiki')}>{k.folderWiki}</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setGenerateAction('bulk-wiki')}>{k.bulkWiki}</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setGenerateAction('hierarchical')}>
                  {k.hierarchicalWiki}
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setGenerateAction('curate')}>{k.curateApproved}</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button onClick={() => setRebuildOpen(true)} size="sm" variant="ghost">
              {k.rebuild}
            </Button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          {tab === 'documents' ? (
            <DocumentsTab
              folderId={folderId}
              kbId={kbId}
              keyword={docQuery}
              onFolderChange={id => {
                setFolderId(id)
                setPage(1)
              }}
              onJobsTab={() => setTab('jobs')}
              page={page}
              setPage={setPage}
            />
          ) : null}
          {tab === 'search' ? <SearchTab kbId={kbId} /> : null}
          {tab === 'wiki' ? <WikiTab kbId={kbId} /> : null}
          {tab === 'graph' ? <GraphTab kbId={kbId} /> : null}
          {tab === 'jobs' ? <JobsTab kbId={kbId} /> : null}
          {tab === 'stats' ? <StatsTab kbId={kbId} /> : null}
        </div>
      </div>

      <KnowledgeLlmConfirm
        onClose={() => setGenerateAction(null)}
        onConfirm={async () => {
          if (generateAction) {
            await runGenerate(generateAction)
          }
        }}
        open={Boolean(generateAction)}
      />

      <ConfirmDialog
        description={k.rebuildConfirm}
        onClose={() => setRebuildOpen(false)}
        onConfirm={async () => {
          await rebuildKnowledgeBase(kbId)
          await queryClient.invalidateQueries({ queryKey: knowledgeKeys.all })
          notify({ kind: 'success', message: k.rebuildQueued })
        }}
        open={rebuildOpen}
        title={k.rebuild}
      />
    </PageSearchShell>
  )
}

function StatsTab({ kbId }: { kbId: string }) {
  const { t } = useI18n()
  const k = t.knowledge
  const statsQuery = useQuery({
    queryFn: () => getKnowledgeStats(kbId),
    queryKey: knowledgeKeys.stats(kbId)
  })

  if (statsQuery.isPending && !statsQuery.data) {
    return <PageLoader label={t.common.loading} />
  }

  const stats = statsQuery.data

  if (!stats) {
    return <PanelEmpty icon="warning" title={k.failedLoad} />
  }

  const tiles = [
    { label: k.statsTotal, value: String(stats.total_documents) },
    { label: k.statsCompleted, value: String(stats.completed) },
    { label: k.statsProcessing, value: String(stats.processing) },
    { label: k.statsFailed, value: String(stats.failed) },
    { label: k.statsOrphaned, value: String(stats.orphaned) },
    { label: k.statsSize, value: formatBytes(stats.total_size) }
  ]

  return (
    <div className="grid grid-cols-2 gap-x-10 gap-y-8 px-8 py-6 sm:grid-cols-3">
      {tiles.map(tile => (
        <div key={tile.label}>
          <div className="text-2xl font-medium tabular-nums tracking-tight">{tile.value}</div>
          <div className="mt-1 text-xs text-muted-foreground">{tile.label}</div>
        </div>
      ))}
    </div>
  )
}
