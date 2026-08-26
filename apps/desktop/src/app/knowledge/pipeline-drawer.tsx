import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import {
  buildGraph,
  deleteChunk,
  generateDocWiki,
  generateSummary,
  getDocumentPreview,
  getKnowledgeDocument,
  type KnowledgeChunk,
  type KnowledgeDocument,
  listDocumentChunks,
  listVectorizationJobs,
  startVectorize,
  updateChunk
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
import { Progress } from '@/components/ui/progress'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/i18n'
import { ChevronDown } from '@/lib/icons'
import { queryClient } from '@/lib/query-client'
import { notify, notifyError } from '@/store/notifications'

import { ackWasSkipped, formatBytes, isActiveParseStatus, jobProgressFraction } from './format'
import { knowledgeKeys } from './keys'
import { KnowledgeLlmConfirm } from './llm-confirm'
import { ParseStatusBadge } from './status'

export function KnowledgePipelineDrawer({
  doc,
  kbId,
  onClose,
  open
}: {
  doc: KnowledgeDocument | null
  kbId: string
  onClose: () => void
  open: boolean
}) {
  const { t } = useI18n()
  const k = t.knowledge
  const docId = doc?.id
  const [busy, setBusy] = useState<null | string>(null)
  const [llmAction, setLlmAction] = useState<null | 'graph' | 'summary' | 'wiki' | 'wiki-curate'>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [showChunks, setShowChunks] = useState(true)
  const [editingId, setEditingId] = useState<null | string>(null)
  const [editingContent, setEditingContent] = useState('')
  const [pendingChunk, setPendingChunk] = useState<KnowledgeChunk | null>(null)

  const liveQuery = useQuery({
    enabled: open && Boolean(docId),
    queryFn: () => getKnowledgeDocument(docId!),
    queryKey: knowledgeKeys.doc(docId ?? ''),
    refetchInterval: query => (isActiveParseStatus(query.state.data?.parse_status) ? 2_500 : false)
  })

  const chunksQuery = useQuery({
    enabled: open && Boolean(docId),
    queryFn: () => listDocumentChunks(docId!),
    queryKey: knowledgeKeys.chunks(docId ?? '')
  })

  const jobsQuery = useQuery({
    enabled: open && Boolean(kbId),
    queryFn: () => listVectorizationJobs(kbId),
    queryKey: knowledgeKeys.vectorJobs(kbId),
    refetchInterval: query => {
      const jobs = query.state.data?.jobs ?? []

      return jobs.some(job => job.doc_id === docId && (job.status === 'processing' || job.status === 'pending'))
        ? 2_500
        : false
    }
  })

  const previewQuery = useQuery({
    enabled: open && showPreview && Boolean(docId),
    queryFn: () => getDocumentPreview(docId!),
    queryKey: knowledgeKeys.preview(docId ?? '')
  })

  const liveDoc = liveQuery.data ?? doc
  const chunks = chunksQuery.data?.chunks ?? []
  const job = (jobsQuery.data?.jobs ?? []).find(item => item.doc_id === docId) ?? null
  const canEnrich = liveDoc?.parse_status === 'completed'

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

  async function handleLlmConfirm() {
    const action = llmAction
    const id = liveDoc?.id

    if (!action || !id) {
      return
    }

    setLlmAction(null)

    if (action === 'summary') {
      await runPipeline('summary', () => generateSummary(id))
      return
    }

    if (action === 'graph') {
      await runPipeline('graph', () => buildGraph(id))
      return
    }

    await runPipeline(action, () => generateDocWiki(id, action === 'wiki-curate'))
  }

  return (
    <Sheet onOpenChange={value => !value && onClose()} open={open}>
      <SheetContent className="sm:max-w-[35rem]" side="right">
        <SheetHeader>
          <SheetTitle className="pr-8">{liveDoc?.file_name ?? k.tabDocuments}</SheetTitle>
          <SheetDescription>
            {liveDoc ? `${formatBytes(liveDoc.file_size)} · ${k.chunks} ${liveDoc.chunk_count}` : ''}
          </SheetDescription>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
          {!liveDoc ? (
            <PageLoader label={t.common.loading} />
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center gap-1.5">
                <ParseStatusBadge status={liveDoc.parse_status} />
                <span className="text-[0.65rem] text-muted-foreground">
                  {liveDoc.chunk_count} {k.chunks}
                </span>
                {liveDoc.summary_status ? (
                  <span className="text-[0.65rem] text-muted-foreground">
                    {k.summary} · {liveDoc.summary_status}
                  </span>
                ) : null}
              </div>

              {liveDoc.error_message ? (
                <p className="text-xs text-destructive">{liveDoc.error_message}</p>
              ) : null}

              {liveDoc.parse_status === 'processing' && job ? (
                <div className="flex flex-col gap-1">
                  <Progress
                    indeterminate={job.progress <= 0}
                    value={jobProgressFraction(job.progress)}
                  />
                  <span className="text-[0.65rem] text-muted-foreground">
                    {job.chunks_done ?? 0} / {job.chunks_total || liveDoc.chunk_count || '…'}
                  </span>
                </div>
              ) : null}

              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={liveDoc.parse_status === 'processing' || busy === 'embed'}
                  onClick={() => void runPipeline('embed', () => startVectorize(liveDoc.id))}
                  size="sm"
                  variant="secondary"
                >
                  {liveDoc.parse_status === 'completed' ? k.revectorize : k.vectorize}
                </Button>
                <Button
                  disabled={!canEnrich || busy === 'summary'}
                  onClick={() => setLlmAction('summary')}
                  size="sm"
                  variant="secondary"
                >
                  {k.summary}
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button disabled={!canEnrich || busy === 'wiki' || busy === 'wiki-curate'} size="sm" variant="secondary">
                      {k.wiki}
                      <ChevronDown />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    <DropdownMenuItem onSelect={() => setLlmAction('wiki')}>{k.wikiOnly}</DropdownMenuItem>
                    <DropdownMenuItem onSelect={() => setLlmAction('wiki-curate')}>{k.wikiAndCurate}</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button
                  disabled={!canEnrich || busy === 'graph'}
                  onClick={() => setLlmAction('graph')}
                  size="sm"
                  variant="secondary"
                >
                  {k.graph}
                </Button>
              </div>

              {liveDoc.summary_text ? (
                <section>
                  <h4 className="mb-1.5 text-[0.65rem] font-medium uppercase tracking-wider text-muted-foreground">
                    {k.summary}
                  </h4>
                  <p className="whitespace-pre-wrap text-xs leading-relaxed text-(--ui-text-secondary)">
                    {liveDoc.summary_text}
                  </p>
                </section>
              ) : null}

              <section>
                <button
                  className="mb-2 text-[0.65rem] font-medium uppercase tracking-wider text-muted-foreground hover:text-foreground"
                  onClick={() => setShowPreview(value => !value)}
                  type="button"
                >
                  {showPreview ? t.common.collapse : t.common.expand} · {k.preview}
                </button>
                {showPreview ? (
                  previewQuery.isPending ? (
                    <p className="text-xs text-muted-foreground">{t.common.loading}</p>
                  ) : previewQuery.data?.content ? (
                    <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-[0.7rem] leading-relaxed text-(--ui-text-secondary)">
                      {previewQuery.data.content}
                    </pre>
                  ) : (
                    <p className="text-xs text-muted-foreground">{k.noPreview}</p>
                  )
                ) : null}
              </section>

              <section>
                <button
                  className="mb-2 text-[0.65rem] font-medium uppercase tracking-wider text-muted-foreground hover:text-foreground"
                  onClick={() => setShowChunks(value => !value)}
                  type="button"
                >
                  {showChunks ? t.common.collapse : t.common.expand} · {k.chunks} ({chunks.length})
                </button>
                {showChunks ? (
                  chunksQuery.isPending && !chunksQuery.data ? (
                    <p className="text-xs text-muted-foreground">{t.common.loading}</p>
                  ) : chunks.length === 0 ? (
                    <p className="text-xs text-muted-foreground">{k.noChunks}</p>
                  ) : (
                    <ul className="flex flex-col">
                      {chunks.map(chunk => (
                        <li className="border-t border-(--ui-stroke-tertiary) py-2.5 first:border-t-0" key={chunk.id}>
                          <div className="mb-1.5 flex items-center justify-between gap-2 text-[0.65rem] text-muted-foreground">
                            <span>
                              #{chunk.chunk_index + 1} · {chunk.char_count}
                            </span>
                            <div className="flex items-center gap-2">
                              <Switch
                                checked={chunk.is_enabled}
                                onCheckedChange={value => {
                                  void updateChunk(chunk.id, { is_enabled: value })
                                    .then(() => queryClient.invalidateQueries({ queryKey: knowledgeKeys.chunks(liveDoc.id) }))
                                    .catch(err => notifyError(err, k.actionFailed))
                                }}
                                size="xs"
                              />
                              <Button
                                onClick={() => {
                                  setEditingId(chunk.id)
                                  setEditingContent(chunk.content)
                                }}
                                size="xs"
                                variant="text"
                              >
                                {k.editChunk}
                              </Button>
                              <Button onClick={() => setPendingChunk(chunk)} size="xs" variant="text">
                                {t.common.delete}
                              </Button>
                            </div>
                          </div>
                          {editingId === chunk.id ? (
                            <div className="flex flex-col gap-2">
                              <Textarea
                                onChange={event => setEditingContent(event.target.value)}
                                rows={6}
                                value={editingContent}
                              />
                              <div className="flex justify-end gap-2">
                                <Button onClick={() => setEditingId(null)} size="xs" variant="text">
                                  {t.common.cancel}
                                </Button>
                                <Button
                                  onClick={() => {
                                    void updateChunk(chunk.id, { content: editingContent })
                                      .then(async () => {
                                        setEditingId(null)
                                        await queryClient.invalidateQueries({ queryKey: knowledgeKeys.chunks(liveDoc.id) })
                                        notify({ kind: 'success', message: t.common.save })
                                      })
                                      .catch(err => notifyError(err, k.actionFailed))
                                  }}
                                  size="xs"
                                >
                                  {t.common.save}
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <p className="line-clamp-6 whitespace-pre-wrap text-xs leading-relaxed text-(--ui-text-secondary)">
                              {chunk.content}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  )
                ) : null}
              </section>
            </div>
          )}
        </div>
      </SheetContent>

      <KnowledgeLlmConfirm
        onClose={() => setLlmAction(null)}
        onConfirm={handleLlmConfirm}
        open={Boolean(llmAction)}
      />

      <ConfirmDialog
        confirmLabel={t.common.delete}
        description={k.deleteChunkConfirm}
        destructive
        onClose={() => setPendingChunk(null)}
        onConfirm={async () => {
          if (!pendingChunk || !liveDoc) {
            return
          }

          await deleteChunk(pendingChunk.id)
          await queryClient.invalidateQueries({ queryKey: knowledgeKeys.chunks(liveDoc.id) })
          notify({ kind: 'success', message: k.deleted })
        }}
        open={Boolean(pendingChunk)}
        title={t.common.delete}
      />
    </Sheet>
  )
}
