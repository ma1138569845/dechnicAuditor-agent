import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import { MarkdownPreview } from '@/app/chat/right-rail/preview-file'
import {
  buildGraph,
  deleteChunk,
  generateDocWiki,
  generateSummary,
  getDocumentFilePayload,
  getDocumentPreview,
  getKnowledgeDocument,
  type DocFilePayload,
  type KnowledgeChunk,
  type KnowledgeDocument,
  listDocumentChunks,
  listVectorizationJobs,
  startVectorize,
  updateChunk
} from '@/api/knowledge'
import { CompactMarkdown } from '@/components/chat/compact-markdown'
import { OfficePreview } from '@/components/chat/office-preview'
import { PageLoader } from '@/components/page-loader'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { Progress } from '@/components/ui/progress'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/i18n'
import { MoreHorizontal, X } from '@/lib/icons'
import { queryClient } from '@/lib/query-client'
import { cn } from '@/lib/utils'
import { notify, notifyError } from '@/store/notifications'

import {
  ackWasSkipped,
  chunkHeading,
  decodeBase64Bytes,
  formatBytes,
  isActiveParseStatus,
  jobProgressFraction,
  looksLikePdf,
  officeKindForFile,
  previewFillsPane,
  previewKindForFile,
  type KnowledgeOfficeKind
} from './format'
import { knowledgeKeys } from './keys'
import { KnowledgeLlmConfirm } from './llm-confirm'
import { ParseStatusBadge } from './status'

type InspectorTab = 'chunks' | 'preview' | 'summary'
type LlmAction = 'graph' | 'summary' | 'wiki'

export function KnowledgePipelineDrawer({
  doc,
  kbId,
  onClose
}: {
  doc: KnowledgeDocument
  kbId: string
  onClose: () => void
}) {
  const { t } = useI18n()
  const k = t.knowledge
  const docId = doc.id
  const [busy, setBusy] = useState<null | string>(null)
  const [llmAction, setLlmAction] = useState<null | LlmAction>(null)
  const [tab, setTab] = useState<InspectorTab>('preview')
  const [editingId, setEditingId] = useState<null | string>(null)
  const [editingContent, setEditingContent] = useState('')
  const [pendingChunk, setPendingChunk] = useState<KnowledgeChunk | null>(null)

  useEffect(() => {
    setTab('preview')
    setEditingId(null)
    setLlmAction(null)
  }, [docId])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape' && !llmAction && !pendingChunk) {
        onClose()
      }
    }

    window.addEventListener('keydown', onKey)

    return () => window.removeEventListener('keydown', onKey)
  }, [llmAction, onClose, pendingChunk])

  const liveQuery = useQuery({
    queryFn: () => getKnowledgeDocument(docId),
    queryKey: knowledgeKeys.doc(docId),
    refetchInterval: query => (isActiveParseStatus(query.state.data?.parse_status) ? 2_500 : false)
  })

  const chunksQuery = useQuery({
    enabled: tab === 'chunks',
    queryFn: () => listDocumentChunks(docId),
    queryKey: knowledgeKeys.chunks(docId)
  })

  const jobsQuery = useQuery({
    queryFn: () => listVectorizationJobs(kbId),
    queryKey: knowledgeKeys.vectorJobs(kbId),
    refetchInterval: query => {
      const jobs = query.state.data?.jobs ?? []

      return jobs.some(job => job.doc_id === docId && (job.status === 'processing' || job.status === 'pending'))
        ? 2_500
        : false
    }
  })

  const liveDoc = liveQuery.data ?? doc
  const chunks = chunksQuery.data?.chunks ?? []
  const job = (jobsQuery.data?.jobs ?? []).find(item => item.doc_id === docId) ?? null
  const canEnrich = liveDoc.parse_status === 'completed'
  const tabs: { id: InspectorTab; label: string }[] = [
    { id: 'preview', label: k.preview },
    { id: 'summary', label: k.summary },
    { id: 'chunks', label: k.chunks }
  ]

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: knowledgeKeys.all })
  }

  async function runPipeline(key: string, fn: () => Promise<unknown>) {
    setBusy(key)

    try {
      const result = await fn()
      notify({ kind: 'success', message: ackWasSkipped(result) ? k.wikiSkipped : k.actionStarted })
      await refresh()
    } catch (err) {
      notifyError(err, k.actionFailed)
    } finally {
      setBusy(null)
    }
  }

  async function handleLlmConfirm(opts?: { curate?: boolean }) {
    const action = llmAction
    setLlmAction(null)

    if (action === 'summary') {
      await runPipeline('summary', () => generateSummary(docId))
      setTab('summary')
      return
    }

    if (action === 'graph') {
      await runPipeline('graph', () => buildGraph(docId))
      return
    }

    if (action === 'wiki') {
      await runPipeline('wiki', () => generateDocWiki(docId, Boolean(opts?.curate)))
    }
  }

  return (
    <aside className="flex h-full min-h-0 w-[min(42rem,48%)] shrink-0 flex-col border-l border-(--ui-stroke-tertiary) bg-(--ui-chat-surface-background)">
      <header className="shrink-0 border-b border-(--ui-stroke-tertiary) px-4 pt-3">
        <div className="flex items-start gap-2">
          <h2 className="min-w-0 flex-1 truncate text-sm font-semibold" title={liveDoc.file_name}>
            {liveDoc.file_name}
          </h2>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button aria-label={k.moreActions} disabled={Boolean(busy)} size="xs" variant="ghost">
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                disabled={liveDoc.parse_status === 'processing' || busy === 'embed'}
                onSelect={() => void runPipeline('embed', () => startVectorize(liveDoc.id))}
              >
                {liveDoc.parse_status === 'completed' ? k.revectorize : k.vectorize}
              </DropdownMenuItem>
              <DropdownMenuItem disabled={!canEnrich || busy === 'summary'} onSelect={() => setLlmAction('summary')}>
                {k.generateSummary}
              </DropdownMenuItem>
              <DropdownMenuItem disabled={!canEnrich || busy === 'wiki'} onSelect={() => setLlmAction('wiki')}>
                {k.generateWiki}
              </DropdownMenuItem>
              <DropdownMenuItem disabled={!canEnrich || busy === 'graph'} onSelect={() => setLlmAction('graph')}>
                {k.buildGraph}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button aria-label={t.common.close} onClick={onClose} size="xs" variant="ghost">
            <X />
          </Button>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[0.7rem] text-muted-foreground">
          <span>
            {(liveDoc.file_type || 'FILE').toUpperCase()} · {formatBytes(liveDoc.file_size)} · {liveDoc.chunk_count}{' '}
            {k.chunks}
          </span>
          <ParseStatusBadge status={liveDoc.parse_status} />
        </div>
        {liveDoc.error_message ? <p className="mt-1.5 text-xs text-destructive">{liveDoc.error_message}</p> : null}
        {liveDoc.parse_status === 'processing' && job ? (
          <div className="mt-2 flex flex-col gap-1 pb-1">
            <Progress indeterminate={job.progress <= 0} value={jobProgressFraction(job.progress)} />
            <span className="text-[0.65rem] text-muted-foreground">
              {job.chunks_done ?? 0} / {job.chunks_total || liveDoc.chunk_count || '…'}
            </span>
          </div>
        ) : null}
        <div className="mt-2.5 flex gap-4">
          {tabs.map(item => (
            <button
              className={cn(
                'pb-2 text-xs transition-colors',
                tab === item.id
                  ? 'font-semibold text-foreground shadow-[inset_0_-2px_0_var(--ui-accent)]'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              key={item.id}
              onClick={() => setTab(item.id)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>

      <div
        className={cn(
          'min-h-0 flex-1',
          tab === 'preview' && previewFillsPane(previewKindForFile(liveDoc.file_name))
            ? 'flex flex-col overflow-hidden'
            : 'overflow-y-auto'
        )}
      >
        {liveQuery.isPending && !liveQuery.data ? (
          <PageLoader label={t.common.loading} />
        ) : tab === 'preview' ? (
          <div className="min-h-0 flex-1">
            <InspectorPreview docId={docId} fileName={liveDoc.file_name} />
          </div>
        ) : tab === 'summary' ? (
          <InspectorSummary
            canGenerate={canEnrich && busy !== 'summary'}
            onGenerate={() => setLlmAction('summary')}
            text={liveDoc.summary_text}
          />
        ) : (
          <InspectorChunks
            chunks={chunks}
            editingContent={editingContent}
            editingId={editingId}
            loading={chunksQuery.isPending && !chunksQuery.data}
            onDelete={setPendingChunk}
            onEdit={(id, content) => {
              setEditingId(id)
              setEditingContent(content)
            }}
            onEditChange={setEditingContent}
            onEditClose={() => setEditingId(null)}
            onSave={content => {
              if (!editingId) {
                return
              }

              void updateChunk(editingId, { content })
                .then(async () => {
                  setEditingId(null)
                  await queryClient.invalidateQueries({ queryKey: knowledgeKeys.chunks(docId) })
                  notify({ kind: 'success', message: t.common.save })
                })
                .catch(err => notifyError(err, k.actionFailed))
            }}
            onToggle={(id, enabled) => {
              void updateChunk(id, { is_enabled: enabled })
                .then(() => queryClient.invalidateQueries({ queryKey: knowledgeKeys.chunks(docId) }))
                .catch(err => notifyError(err, k.actionFailed))
            }}
          />
        )}
      </div>

      <KnowledgeLlmConfirm
        onClose={() => setLlmAction(null)}
        onConfirm={handleLlmConfirm}
        open={Boolean(llmAction)}
        variant={llmAction === 'wiki' ? 'wiki' : 'default'}
      />

      <ConfirmDialog
        confirmLabel={t.common.delete}
        description={k.deleteChunkConfirm}
        destructive
        onClose={() => setPendingChunk(null)}
        onConfirm={async () => {
          if (!pendingChunk) {
            return
          }

          await deleteChunk(pendingChunk.id)
          await queryClient.invalidateQueries({ queryKey: knowledgeKeys.chunks(docId) })
          notify({ kind: 'success', message: k.deleted })
        }}
        open={Boolean(pendingChunk)}
        title={t.common.delete}
      />
    </aside>
  )
}

function InspectorPreview({ docId, fileName }: { docId: string; fileName: string }) {
  const { t } = useI18n()
  const k = t.knowledge
  const kind = previewKindForFile(fileName)
  const officeKind = officeKindForFile(fileName)
  const needsBinary = kind === 'pdf' || kind === 'image' || kind === 'office'
  const payloadQuery = useQuery({
    enabled: needsBinary,
    queryFn: () => getDocumentFilePayload(docId),
    queryKey: knowledgeKeys.file(docId)
  })
  const payloadReady = Boolean(payloadQuery.data && !payloadQuery.data.too_large && payloadQuery.data.data)
  const wantText =
    kind === 'markdown' ||
    kind === 'text' ||
    kind === 'excerpt' ||
    Boolean(payloadQuery.data?.too_large) ||
    payloadQuery.isError ||
    (needsBinary && payloadQuery.isSuccess && !payloadReady)
  const textQuery = useQuery({
    enabled: wantText,
    queryFn: () => getDocumentPreview(docId),
    queryKey: knowledgeKeys.preview(docId)
  })

  if (needsBinary && payloadQuery.isPending) {
    return <p className="px-4 py-6 text-xs text-muted-foreground">{t.common.loading}</p>
  }

  if (kind === 'office' && officeKind && payloadReady && payloadQuery.data?.data) {
    return <OfficeBytesPreview data={payloadQuery.data.data} officeKind={officeKind} />
  }

  if (needsBinary && payloadReady && payloadQuery.data) {
    return <BinaryPreview payload={payloadQuery.data} title={fileName} />
  }

  if (textQuery.isPending) {
    return <p className="px-4 py-6 text-xs text-muted-foreground">{t.common.loading}</p>
  }

  const content = textQuery.data?.content

  if (!content) {
    return (
      <p className="px-4 py-6 text-xs text-muted-foreground">
        {payloadQuery.data?.too_large ? k.previewTooLarge : k.noPreview}
      </p>
    )
  }

  if (kind === 'markdown') {
    return <MarkdownPreview text={content} />
  }

  return (
    <div className="px-4 py-3">
      {payloadQuery.data?.too_large ? (
        <p className="mb-2 text-[0.7rem] text-muted-foreground">{k.previewTooLarge}</p>
      ) : kind === 'excerpt' || kind === 'office' || kind === 'pdf' || kind === 'image' ? (
        <p className="mb-2 text-[0.65rem] font-medium uppercase tracking-wider text-muted-foreground">{k.textExcerpt}</p>
      ) : null}
      <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-foreground">{content}</pre>
    </div>
  )
}

function OfficeBytesPreview({ data, officeKind }: { data: string; officeKind: KnowledgeOfficeKind }) {
  const arrayBuffer = useMemo(() => {
    const bytes = decodeBase64Bytes(data)
    const copy = new ArrayBuffer(bytes.byteLength)

    new Uint8Array(copy).set(bytes)

    return copy
  }, [data])

  return (
    <div className="h-full min-h-0">
      <OfficePreview arrayBuffer={arrayBuffer} officeKind={officeKind} />
    </div>
  )
}

function payloadToObjectUrl(payload: DocFilePayload): string {
  const bytes = decodeBase64Bytes(payload.data ?? '')
  const mime = payload.kind === 'pdf' || payload.mime === 'application/pdf' ? 'application/pdf' : payload.mime

  return URL.createObjectURL(new Blob([bytes], { type: mime || 'application/octet-stream' }))
}

function BinaryPreview({ payload, title }: { payload: DocFilePayload; title: string }) {
  const { t } = useI18n()
  const [url, setUrl] = useState<string>()
  const [invalidPdf, setInvalidPdf] = useState(false)

  useEffect(() => {
    const bytes = decodeBase64Bytes(payload.data ?? '')

    if (payload.kind === 'pdf' && !looksLikePdf(bytes)) {
      setInvalidPdf(true)
      setUrl(undefined)

      return
    }

    setInvalidPdf(false)
    const objectUrl = payloadToObjectUrl(payload)
    setUrl(objectUrl)

    return () => URL.revokeObjectURL(objectUrl)
  }, [payload])

  if (invalidPdf) {
    return <p className="px-4 py-6 text-xs text-muted-foreground">{t.knowledge.noPreview}</p>
  }

  if (!url) {
    return null
  }

  if (payload.kind === 'image') {
    return (
      <div className="h-full overflow-auto">
        <img alt={title} className="mx-auto max-w-full p-4" src={url} />
      </div>
    )
  }

  return (
    <div className="h-full min-h-0 w-full overflow-hidden bg-white">
      <iframe className="h-full w-full border-0 bg-white" src={url} title={title} />
    </div>
  )
}

function InspectorSummary({
  canGenerate,
  onGenerate,
  text
}: {
  canGenerate: boolean
  onGenerate: () => void
  text: null | string
}) {
  const { t } = useI18n()
  const k = t.knowledge

  if (!text?.trim()) {
    return (
      <div className="flex flex-col items-start gap-2 px-4 py-6">
        <p className="text-sm font-medium">{k.noSummary}</p>
        <p className="text-xs text-muted-foreground">{k.noSummaryDesc}</p>
        <Button disabled={!canGenerate} onClick={onGenerate} size="xs" variant="secondary">
          {k.generateSummary}
        </Button>
      </div>
    )
  }

  return (
    <div className="px-4 py-4">
      <CompactMarkdown className="text-(--ui-text-secondary)" text={text} />
    </div>
  )
}

function InspectorChunks({
  chunks,
  editingContent,
  editingId,
  loading,
  onDelete,
  onEdit,
  onEditChange,
  onEditClose,
  onSave,
  onToggle
}: {
  chunks: KnowledgeChunk[]
  editingContent: string
  editingId: null | string
  loading: boolean
  onDelete: (chunk: KnowledgeChunk) => void
  onEdit: (id: string, content: string) => void
  onEditChange: (value: string) => void
  onEditClose: () => void
  onSave: (content: string) => void
  onToggle: (id: string, enabled: boolean) => void
}) {
  const { t } = useI18n()
  const k = t.knowledge

  if (loading) {
    return <p className="px-4 py-6 text-xs text-muted-foreground">{t.common.loading}</p>
  }

  if (chunks.length === 0) {
    return <p className="px-4 py-6 text-xs text-muted-foreground">{k.noChunks}</p>
  }

  return (
    <ul>
      {chunks.map(chunk => (
        <li
          className={cn(
            'group border-t border-(--ui-stroke-tertiary) px-4 py-2.5 first:border-t-0',
            !chunk.is_enabled && 'opacity-50'
          )}
          key={chunk.id}
        >
          <div className="mb-1 flex items-center gap-2 text-[0.65rem] text-muted-foreground">
            <span>
              #{chunk.chunk_index + 1} · {chunk.char_count}
              {chunk.is_enabled ? '' : ` · ${k.chunkOff}`}
            </span>
            <b className="min-w-0 truncate font-semibold text-foreground">
              {chunkHeading(chunk.content, chunk.chunk_index)}
            </b>
            <Button
              className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
              onClick={() => onEdit(chunk.id, chunk.content)}
              size="xs"
              variant="text"
            >
              {k.editChunk}
            </Button>
            <Button
              className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
              onClick={() => onDelete(chunk)}
              size="xs"
              variant="text"
            >
              {t.common.delete}
            </Button>
            <Switch
              checked={chunk.is_enabled}
              className="ml-auto"
              onCheckedChange={value => onToggle(chunk.id, value)}
              size="xs"
            />
          </div>
          {editingId === chunk.id ? (
            <div className="flex flex-col gap-2">
              <Textarea onChange={event => onEditChange(event.target.value)} rows={6} value={editingContent} />
              <div className="flex justify-end gap-2">
                <Button onClick={onEditClose} size="xs" variant="text">
                  {t.common.cancel}
                </Button>
                <Button onClick={() => onSave(editingContent)} size="xs">
                  {t.common.save}
                </Button>
              </div>
            </div>
          ) : (
            <div className="line-clamp-3">
              <CompactMarkdown text={chunk.content} />
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}
