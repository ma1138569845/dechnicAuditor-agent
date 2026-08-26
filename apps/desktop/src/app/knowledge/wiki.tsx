import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { MarkdownPreview } from '@/app/chat/right-rail/preview-file'
import {
  evaluateWikiQuality,
  getWikiPage,
  listKnowledgeWiki,
  type WikiPage,
  type WikiReviewStatus,
  updateWikiReview
} from '@/api/knowledge'
import { PageLoader } from '@/components/page-loader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useI18n } from '@/i18n'
import { X } from '@/lib/icons'
import { queryClient } from '@/lib/query-client'
import { cn } from '@/lib/utils'
import { notify, notifyError } from '@/store/notifications'

import { PanelEmpty } from '../overlays/panel'

import { formatKbDate, wikiArticleMarkdown } from './format'
import { knowledgeKeys } from './keys'
import { KnowledgeLlmConfirm } from './llm-confirm'
import { ReviewStatusBadge } from './status'

type WikiFilter = 'all' | WikiReviewStatus

export function WikiTab({ kbId }: { kbId: string }) {
  const { t } = useI18n()
  const k = t.knowledge
  const [filter, setFilter] = useState<WikiFilter>('all')
  const [activeId, setActiveId] = useState<null | string>(null)
  const wikiQuery = useQuery({
    queryFn: () => listKnowledgeWiki(kbId, { review_status: filter === 'all' ? undefined : filter }),
    queryKey: knowledgeKeys.wiki(kbId, filter)
  })
  const pageQuery = useQuery({
    enabled: Boolean(activeId),
    queryFn: () => getWikiPage(activeId!),
    queryKey: knowledgeKeys.wikiPage(activeId ?? '')
  })

  const pages = wikiQuery.data?.pages ?? []
  const listPage = pages.find(page => page.id === activeId) ?? null
  const page = pageQuery.data ?? listPage

  useEffect(() => {
    setActiveId(null)
  }, [filter, kbId])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape' && activeId) {
        setActiveId(null)
      }
    }

    window.addEventListener('keydown', onKey)

    return () => window.removeEventListener('keydown', onKey)
  }, [activeId])

  if (wikiQuery.isPending && !wikiQuery.data) {
    return <PageLoader label={t.common.loading} />
  }

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col px-6 pb-6">
        <div className="flex items-center gap-2 pb-4">
          <Select onValueChange={value => setFilter(value as WikiFilter)} value={filter}>
            <SelectTrigger className="w-44" size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{k.reviewAll}</SelectItem>
              <SelectItem value="pending">{k.reviewPending}</SelectItem>
              <SelectItem value="approved">{k.reviewApproved}</SelectItem>
              <SelectItem value="rejected">{k.reviewRejected}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {pages.length === 0 ? (
          <PanelEmpty description={k.noWikiDesc} icon="book" title={k.noWikiTitle} />
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="grid grid-cols-[repeat(auto-fill,minmax(16rem,1fr))] gap-3">
              {pages.map(item => (
                <button
                  className={cn(
                    'rounded-md border border-(--ui-stroke-tertiary) px-3.5 py-3 text-left hover:bg-(--ui-control-hover-background)',
                    activeId === item.id && 'border-(--ui-stroke-secondary) bg-(--ui-control-active-background)'
                  )}
                  key={item.id}
                  onClick={() => setActiveId(item.id)}
                  type="button"
                >
                  <span className="block truncate text-sm font-medium">{item.title}</span>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <ReviewStatusBadge status={item.review_status || item.status} />
                    {item.source ? (
                      <Badge size="xs" variant="outline">
                        {item.source}
                      </Badge>
                    ) : null}
                    {item.quality_score != null ? (
                      <Badge size="xs" variant="muted">
                        {k.quality} {Number(item.quality_score).toFixed(1)}
                      </Badge>
                    ) : null}
                  </div>
                  <span className="mt-1.5 block text-[0.65rem] text-muted-foreground">
                    {formatKbDate(item.updated_at)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {activeId ? (
        <WikiArticlePane
          kbId={kbId}
          onClose={() => setActiveId(null)}
          page={page}
          pending={pageQuery.isPending && !pageQuery.data}
        />
      ) : null}
    </div>
  )
}

function WikiArticlePane({
  kbId,
  onClose,
  page,
  pending
}: {
  kbId: string
  onClose: () => void
  page: null | WikiPage
  pending: boolean
}) {
  const { t } = useI18n()
  const k = t.knowledge
  const [evaluateOpen, setEvaluateOpen] = useState(false)
  const markdown = page?.content ? wikiArticleMarkdown(page.content, page.title) : ''

  async function handleReview(status: WikiReviewStatus) {
    if (!page) {
      return
    }

    try {
      await updateWikiReview(page.id, status)
      await queryClient.invalidateQueries({ queryKey: knowledgeKeys.wikiPage(page.id) })
      await queryClient.invalidateQueries({ queryKey: ['knowledge', 'wiki', kbId] })
      notify({ kind: 'success', message: t.common.save })
    } catch (err) {
      notifyError(err, k.actionFailed)
    }
  }

  return (
    <aside className="flex h-full min-h-0 w-[min(42rem,52%)] shrink-0 flex-col border-l border-(--ui-stroke-tertiary) bg-(--ui-chat-surface-background)">
      <header className="shrink-0 border-b border-(--ui-stroke-tertiary) px-5 pt-4 pb-3">
        <div className="flex items-start gap-2">
          <h2 className="min-w-0 flex-1 text-base font-semibold leading-snug tracking-tight">
            {page?.title ?? k.tabWiki}
          </h2>
          <Button aria-label={t.common.close} onClick={onClose} size="xs" variant="ghost">
            <X />
          </Button>
        </div>
        {page ? (
          <p className="mt-1 text-[0.7rem] text-muted-foreground">
            {formatKbDate(page.updated_at)}
            {page.source ? ` · ${page.source}` : ''}
            {page.quality_score != null ? ` · ${k.quality} ${Number(page.quality_score).toFixed(1)}` : ''}
          </p>
        ) : null}
        {page ? (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <ReviewStatusBadge status={page.review_status || page.status} />
            <Button onClick={() => void handleReview('approved')} size="xs" variant="secondary">
              {k.approve}
            </Button>
            <Button onClick={() => void handleReview('rejected')} size="xs" variant="secondary">
              {k.reject}
            </Button>
            <Button onClick={() => void handleReview('pending')} size="xs" variant="ghost">
              {k.reviewPending}
            </Button>
            <Button className="ml-auto" onClick={() => setEvaluateOpen(true)} size="xs" variant="ghost">
              {k.evaluateQuality}
            </Button>
          </div>
        ) : null}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {pending && !page?.content ? (
          <p className="px-5 py-6 text-xs text-muted-foreground">{t.common.loading}</p>
        ) : markdown ? (
          <article className="wiki-article [&_.preview-markdown]:max-w-[40rem] [&_.preview-markdown]:px-6 [&_.preview-markdown]:py-6 [&_.preview-markdown]:text-[0.9375rem] [&_.preview-markdown]:leading-7 [&_.preview-markdown_p:has(>strong:only-child)]:mt-6 [&_.preview-markdown_p:has(>strong:only-child)]:mb-2 [&_.preview-markdown_p:has(>strong:only-child)]:text-lg [&_.preview-markdown_p:has(>strong:only-child)]:font-semibold [&_.preview-markdown_p:has(>strong:only-child)]:tracking-tight [&_.preview-markdown_p:has(>strong:only-child)]:text-foreground">
            <MarkdownPreview text={markdown} />
          </article>
        ) : (
          <p className="px-5 py-6 text-xs text-muted-foreground">{k.noWikiDesc}</p>
        )}
      </div>

      <KnowledgeLlmConfirm
        onClose={() => setEvaluateOpen(false)}
        onConfirm={async () => {
          if (!page) {
            return
          }

          try {
            await evaluateWikiQuality(page.id)
            await queryClient.invalidateQueries({ queryKey: knowledgeKeys.wikiPage(page.id) })
            await queryClient.invalidateQueries({ queryKey: ['knowledge', 'wiki', kbId] })
            notify({ kind: 'success', message: k.qualityUpdated })
          } catch (err) {
            notifyError(err, k.actionFailed)
            throw err
          }
        }}
        open={evaluateOpen}
      />
    </aside>
  )
}
