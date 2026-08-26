import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import {
  evaluateWikiQuality,
  getWikiPage,
  listKnowledgeWiki,
  type WikiPage,
  type WikiReviewStatus,
  updateWikiReview
} from '@/api/knowledge'
import { CompactMarkdown } from '@/components/chat/compact-markdown'
import { PageLoader } from '@/components/page-loader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle
} from '@/components/ui/sheet'
import { useI18n } from '@/i18n'
import { queryClient } from '@/lib/query-client'
import { notify, notifyError } from '@/store/notifications'

import { PanelEmpty } from '../overlays/panel'

import { formatKbDate } from './format'
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

  if (wikiQuery.isPending && !wikiQuery.data) {
    return <PageLoader label={t.common.loading} />
  }

  return (
    <div className="flex h-full min-h-0 flex-col px-6 pb-6">
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
            {pages.map(page => (
              <button
                className="rounded-md border border-(--ui-stroke-tertiary) px-3.5 py-3 text-left hover:bg-(--ui-control-hover-background)"
                key={page.id}
                onClick={() => setActiveId(page.id)}
                type="button"
              >
                <span className="block truncate text-sm font-medium">{page.title}</span>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <ReviewStatusBadge status={page.review_status || page.status} />
                  {page.source ? (
                    <Badge size="xs" variant="outline">
                      {page.source}
                    </Badge>
                  ) : null}
                  {page.quality_score != null ? (
                    <Badge size="xs" variant="muted">
                      {k.quality} {Number(page.quality_score).toFixed(1)}
                    </Badge>
                  ) : null}
                </div>
                <span className="mt-1.5 block text-[0.65rem] text-muted-foreground">
                  {formatKbDate(page.updated_at)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
      <WikiPageSheet
        kbId={kbId}
        onClose={() => setActiveId(null)}
        page={pageQuery.data ?? null}
        pending={pageQuery.isPending && Boolean(activeId)}
      />
    </div>
  )
}

function WikiPageSheet({
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
  const open = Boolean(page) || pending

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
    <Sheet onOpenChange={value => !value && onClose()} open={open}>
      <SheetContent className="sm:max-w-[40rem]" side="right">
        <SheetHeader>
          <SheetTitle className="pr-8">{page?.title ?? k.tabWiki}</SheetTitle>
          <SheetDescription>{page ? formatKbDate(page.updated_at) : ''}</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
          {pending && !page ? (
            <p className="text-xs text-muted-foreground">{t.common.loading}</p>
          ) : page ? (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center gap-2">
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
                <Button onClick={() => setEvaluateOpen(true)} size="xs" variant="ghost">
                  {k.evaluateQuality}
                </Button>
              </div>
              {page.content ? (
                <CompactMarkdown className="text-foreground/90" text={page.content} />
              ) : (
                <p className="text-xs text-muted-foreground">{k.noWikiDesc}</p>
              )}
            </div>
          ) : null}
        </div>
      </SheetContent>
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
    </Sheet>
  )
}
