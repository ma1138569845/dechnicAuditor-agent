import { useQuery } from '@tanstack/react-query'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  type KnowledgeBase,
  listKnowledgeBases
} from '@/api/knowledge'
import { PageLoader } from '@/components/page-loader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/i18n'
import { compactNumber } from '@/lib/format'
import { Plus } from '@/lib/icons'
import { queryClient } from '@/lib/query-client'
import { cn } from '@/lib/utils'
import { notify, notifyError } from '@/store/notifications'

import { useRefreshHotkey } from '../hooks/use-refresh-hotkey'
import { PanelEmpty } from '../overlays/panel'
import { PageSearchShell } from '../page-search-shell'
import { KNOWLEDGE_ROUTE } from '../routes'

import { formatKbDate } from './format'

const BASES_KEY = ['knowledge', 'bases'] as const

function matchesQuery(kb: KnowledgeBase, query: string): boolean {
  if (!query) {
    return true
  }

  const haystack = `${kb.name} ${kb.description}`.toLowerCase()

  return haystack.includes(query.toLowerCase())
}

export function KnowledgeList() {
  const { t } = useI18n()
  const k = t.knowledge
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<KnowledgeBase | null>(null)

  const { data, error, isPending, refetch } = useQuery({
    queryFn: listKnowledgeBases,
    queryKey: BASES_KEY
  })

  useRefreshHotkey(() => void refetch())

  const bases = data?.bases ?? []
  const filtered = useMemo(() => bases.filter(kb => matchesQuery(kb, query.trim())), [bases, query])
  const systemBases = filtered.filter(kb => kb.is_system)
  const userBases = filtered.filter(kb => !kb.is_system)

  if (isPending && !data) {
    return <PageLoader label={t.common.loading} />
  }

  if (error && !data) {
    return (
      <PanelEmpty
        action={
          <Button onClick={() => void refetch()} size="sm" variant="secondary">
            {t.common.retry}
          </Button>
        }
        description={error instanceof Error ? error.message : k.failedLoad}
        icon="warning"
        title={k.failedLoad}
      />
    )
  }

  return (
    <PageSearchShell
      onSearchChange={setQuery}
      searchHidden={bases.length === 0}
      searchPlaceholder={k.searchPlaceholder}
      searchTrailingAction={
        <Button onClick={() => setCreateOpen(true)} size="sm">
          <Plus />
          {k.create}
        </Button>
      }
      searchValue={query}
    >
      <div className="h-full overflow-y-auto overflow-x-hidden px-6 pb-8">
        {bases.length === 0 ? (
          <PanelEmpty
            action={
              <Button onClick={() => setCreateOpen(true)} size="sm">
                <Plus />
                {k.create}
              </Button>
            }
            description={k.emptyDesc}
            icon="book"
            title={k.emptyTitle}
          />
        ) : filtered.length === 0 ? (
          <PanelEmpty description={t.sidebar.noMatch(query)} icon="search" title={k.emptyTitle} />
        ) : (
          <div className="flex flex-col gap-8 pt-2">
            {systemBases.length > 0 ? (
              <KbSection kbs={systemBases} onOpen={id => navigate(`${KNOWLEDGE_ROUTE}/${encodeURIComponent(id)}`)} title={k.systemBases} />
            ) : null}
            <KbSection
              kbs={userBases}
              onDelete={setPendingDelete}
              onOpen={id => navigate(`${KNOWLEDGE_ROUTE}/${encodeURIComponent(id)}`)}
              title={k.userBases}
            />
          </div>
        )}
      </div>

      <CreateKnowledgeDialog onClose={() => setCreateOpen(false)} open={createOpen} />

      <ConfirmDialog
        confirmLabel={t.common.delete}
        description={pendingDelete ? k.deleteConfirm(pendingDelete.name) : undefined}
        destructive
        onClose={() => setPendingDelete(null)}
        onConfirm={async () => {
          if (!pendingDelete) {
            return
          }

          await deleteKnowledgeBase(pendingDelete.id)
          await queryClient.invalidateQueries({ queryKey: BASES_KEY })
          notify({ kind: 'success', message: k.deleted })
        }}
        open={Boolean(pendingDelete)}
        title={t.common.delete}
      />
    </PageSearchShell>
  )
}

function KbSection({
  kbs,
  onDelete,
  onOpen,
  title
}: {
  kbs: KnowledgeBase[]
  onDelete?: (kb: KnowledgeBase) => void
  onOpen: (id: string) => void
  title: string
}) {
  const { t } = useI18n()
  const k = t.knowledge

  if (kbs.length === 0 && onDelete) {
    return (
      <section>
        <h2 className="mb-3 text-[0.65rem] font-medium uppercase tracking-wider text-muted-foreground">{title}</h2>
        <p className="text-xs text-muted-foreground">{k.emptyDesc}</p>
      </section>
    )
  }

  if (kbs.length === 0) {
    return null
  }

  return (
    <section>
      <h2 className="mb-3 text-[0.65rem] font-medium uppercase tracking-wider text-muted-foreground">{title}</h2>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(16.5rem,1fr))] gap-3">
        {kbs.map(kb => (
          <KbCard key={kb.id} kb={kb} onDelete={onDelete} onOpen={() => onOpen(kb.id)} />
        ))}
      </div>
    </section>
  )
}

function KbCard({
  kb,
  onDelete,
  onOpen
}: {
  kb: KnowledgeBase
  onDelete?: (kb: KnowledgeBase) => void
  onOpen: () => void
}) {
  const { t } = useI18n()
  const k = t.knowledge
  const docs = kb.stats?.total_documents ?? 0

  return (
    <div
      className={cn(
        'group relative flex min-h-[8.5rem] flex-col gap-2 rounded-md px-3.5 py-3 text-left transition-colors',
        'border border-(--ui-stroke-tertiary) hover:bg-(--ui-control-hover-background)'
      )}
    >
      <button className="flex min-w-0 flex-1 flex-col gap-2 text-left" onClick={onOpen} type="button">
        <div className="flex items-start gap-2">
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{kb.name}</span>
          {kb.is_system ? (
            <Badge size="xs" variant="muted">
              {k.system}
            </Badge>
          ) : null}
        </div>
        <p className="line-clamp-2 min-h-[2rem] text-xs leading-relaxed text-muted-foreground">
          {kb.description || k.noDescription}
        </p>
        <div className="mt-auto flex items-center justify-between gap-2 pt-1 text-[0.65rem] text-muted-foreground">
          <span>{k.docsCount(compactNumber(docs))}</span>
          <span>{formatKbDate(kb.created_at)}</span>
        </div>
      </button>
      {onDelete && !kb.is_system ? (
        <Button
          className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
          onClick={event => {
            event.stopPropagation()
            onDelete(kb)
          }}
          size="xs"
          variant="text"
        >
          {t.common.delete}
        </Button>
      ) : null}
    </div>
  )
}

function CreateKnowledgeDialog({ onClose, open }: { onClose: () => void; open: boolean }) {
  const { t } = useI18n()
  const k = t.knowledge
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) {
      return
    }

    setName('')
    setDescription('')
    setBusy(false)
  }, [open])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()

    const trimmed = name.trim()

    if (!trimmed || busy) {
      return
    }

    setBusy(true)

    try {
      const created = await createKnowledgeBase(trimmed, description.trim())
      await queryClient.invalidateQueries({ queryKey: BASES_KEY })
      notify({ kind: 'success', message: k.created })
      setName('')
      setDescription('')
      onClose()
      navigate(`${KNOWLEDGE_ROUTE}/${encodeURIComponent(created.id)}`)
    } catch (err) {
      notifyError(err, k.failedCreate)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      onOpenChange={value => {
        if (!value && !busy) {
          onClose()
        }
      }}
      open={open}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{k.createTitle}</DialogTitle>
          <DialogDescription>{k.createDesc}</DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={handleSubmit}>
          <Field htmlFor="kb-name" label={k.nameLabel}>
            <Input
              autoFocus
              id="kb-name"
              maxLength={120}
              onChange={event => setName(event.target.value)}
              placeholder={k.namePlaceholder}
              value={name}
            />
          </Field>
          <Field htmlFor="kb-desc" label={k.descLabel}>
            <Textarea
              id="kb-desc"
              maxLength={500}
              onChange={event => setDescription(event.target.value)}
              placeholder={k.descPlaceholder}
              rows={3}
              value={description}
            />
          </Field>
          <DialogFooter>
            <Button disabled={busy} onClick={onClose} type="button" variant="text">
              {t.common.cancel}
            </Button>
            <Button disabled={!name.trim() || busy} type="submit">
              {busy ? t.common.saving : t.common.confirm}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
