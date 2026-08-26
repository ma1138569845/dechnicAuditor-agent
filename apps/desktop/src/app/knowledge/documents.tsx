import { useQuery } from '@tanstack/react-query'
import { type FormEvent, useEffect, useRef, useState } from 'react'

import {
  bulkDeleteDocuments,
  createKnowledgeFolder,
  deleteKnowledgeDocument,
  deleteKnowledgeFolder,
  type KnowledgeDocument,
  type KnowledgeFolder,
  listAllKnowledgeFolders,
  listKnowledgeDocuments,
  startBulkWiki,
  startVectorize,
  uploadKnowledgeDocument
} from '@/api/knowledge'
import { PageLoader } from '@/components/page-loader'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
import { useI18n } from '@/i18n'
import { Plus, Upload } from '@/lib/icons'
import { queryClient } from '@/lib/query-client'
import { cn } from '@/lib/utils'
import { notify, notifyError } from '@/store/notifications'

import { formatBytes, formatKbDate, isActiveParseStatus } from './format'
import { knowledgeKeys } from './keys'
import { KnowledgeLlmConfirm } from './llm-confirm'
import { KnowledgePipelineDrawer } from './pipeline-drawer'
import { ParseStatusBadge } from './status'

const PAGE_SIZE = 50

export function DocumentsTab({
  folderId,
  kbId,
  keyword,
  onFolderChange,
  onJobsTab,
  page,
  setPage
}: {
  folderId: null | string
  kbId: string
  keyword: string
  onFolderChange: (id: null | string) => void
  onJobsTab: () => void
  page: number
  setPage: (page: number) => void
}) {
  const { t } = useI18n()
  const k = t.knowledge
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [folderOpen, setFolderOpen] = useState(false)
  const [pendingDoc, setPendingDoc] = useState<KnowledgeDocument | null>(null)
  const [pendingFolder, setPendingFolder] = useState<KnowledgeFolder | null>(null)
  const [drawerDoc, setDrawerDoc] = useState<KnowledgeDocument | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [batchBusy, setBatchBusy] = useState(false)
  const [batchWikiOpen, setBatchWikiOpen] = useState(false)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)

  const foldersQuery = useQuery({
    queryFn: () => listAllKnowledgeFolders(kbId),
    queryKey: knowledgeKeys.folders(kbId)
  })

  const docsQuery = useQuery({
    queryFn: () =>
      listKnowledgeDocuments(kbId, {
        folder_id: folderId || undefined,
        keyword: keyword.trim() || undefined,
        page,
        page_size: PAGE_SIZE
      }),
    queryKey: knowledgeKeys.docs(kbId, folderId, keyword.trim(), page),
    refetchInterval: query => {
      const docs = query.state.data?.documents ?? []

      return docs.some(doc => isActiveParseStatus(doc.parse_status)) ? 3_000 : false
    }
  })

  const folders = foldersQuery.data ?? []
  const documents = docsQuery.data?.documents ?? []
  const total = docsQuery.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const allChecked = documents.length > 0 && documents.every(doc => selected.has(doc.id))
  const someChecked = documents.some(doc => selected.has(doc.id))

  useEffect(() => {
    setSelected(new Set())
    setDrawerDoc(null)
  }, [folderId, keyword, page])

  async function handleUpload(files: FileList | null) {
    if (!files || files.length === 0) {
      return
    }

    setUploading(true)

    try {
      for (const file of Array.from(files)) {
        const bytes = await file.arrayBuffer()
        await uploadKnowledgeDocument(
          kbId,
          { bytes, contentType: file.type || undefined, filename: file.name },
          folderId
        )
      }

      await queryClient.invalidateQueries({ queryKey: knowledgeKeys.all })
      notify({ kind: 'success', message: k.uploadSuccess })
    } catch (err) {
      notifyError(err, k.failedUpload)
    } finally {
      setUploading(false)

      if (fileRef.current) {
        fileRef.current.value = ''
      }
    }
  }

  function toggleOne(id: string, checked: boolean) {
    setSelected(prev => {
      const next = new Set(prev)

      if (checked) {
        next.add(id)
      } else {
        next.delete(id)
      }

      return next
    })
  }

  function toggleAll(checked: boolean) {
    setSelected(checked ? new Set(documents.map(doc => doc.id)) : new Set())
  }

  async function handleBatchVectorize() {
    const ids = [...selected]

    if (ids.length === 0) {
      return
    }

    setBatchBusy(true)

    try {
      for (const id of ids) {
        await startVectorize(id)
      }

      setSelected(new Set())
      await queryClient.invalidateQueries({ queryKey: knowledgeKeys.all })
      notify({ kind: 'success', message: k.actionStarted })
    } catch (err) {
      notifyError(err, k.actionFailed)
    } finally {
      setBatchBusy(false)
    }
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className="flex w-52 shrink-0 flex-col border-r border-(--ui-stroke-tertiary)">
        <div className="flex items-center justify-between gap-1 px-3 py-2">
          <span className="text-[0.65rem] font-medium uppercase tracking-wider text-muted-foreground">
            {k.folders}
          </span>
          <Button onClick={() => setFolderOpen(true)} size="xs" variant="ghost">
            <Plus />
            {k.newFolder}
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-3">
          <FolderRow active={folderId === null} depth={0} label={k.allDocuments} onClick={() => onFolderChange(null)} />
          {folders.map(folder => (
            <FolderRow
              active={folderId === folder.id}
              depth={folder.depth + 1}
              key={folder.id}
              label={folder.name}
              onClick={() => onFolderChange(folder.id)}
              onDelete={() => setPendingFolder(folder)}
            />
          ))}
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-end gap-2 px-4 py-2">
          <input
            className="hidden"
            multiple
            onChange={event => void handleUpload(event.target.files)}
            ref={fileRef}
            type="file"
          />
          <Button disabled={uploading} onClick={() => fileRef.current?.click()} size="sm" variant="secondary">
            <Upload />
            {uploading ? k.uploading : k.upload}
          </Button>
        </div>

        {selected.size > 0 ? (
          <div className="flex flex-wrap items-center gap-2 px-4 pb-2 text-xs">
            <span className="text-muted-foreground">{k.selectedCount(selected.size)}</span>
            <Button disabled={batchBusy} onClick={() => void handleBatchVectorize()} size="xs" variant="secondary">
              {k.vectorize}
            </Button>
            <Button disabled={batchBusy} onClick={() => setBatchWikiOpen(true)} size="xs" variant="secondary">
              {k.wiki}
            </Button>
            <Button onClick={() => setBulkDeleteOpen(true)} size="xs" variant="text">
              {t.common.delete}
            </Button>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-auto px-4 pb-4">
          {docsQuery.isPending && !docsQuery.data ? (
            <PageLoader label={t.common.loading} />
          ) : documents.length === 0 ? (
            <PanelEmptyLocal />
          ) : (
            <table className="w-full border-collapse text-left text-xs">
              <thead className="sticky top-0 bg-(--ui-chat-surface-background) text-[0.65rem] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="w-8 px-2 py-2">
                    <Checkbox
                      checked={allChecked ? true : someChecked ? 'indeterminate' : false}
                      onCheckedChange={value => toggleAll(value === true)}
                    />
                  </th>
                  <th className="px-2 py-2 font-medium">{k.fileName}</th>
                  <th className="w-16 px-2 py-2 font-medium">{k.fileType}</th>
                  <th className="w-20 px-2 py-2 font-medium">{k.fileSize}</th>
                  <th className="w-24 px-2 py-2 font-medium">{k.status}</th>
                  <th className="w-16 px-2 py-2 text-center font-medium">{k.chunks}</th>
                  <th className="w-24 px-2 py-2 font-medium">{k.createdAt}</th>
                  <th className="w-36 px-2 py-2 font-medium">{k.actions}</th>
                </tr>
              </thead>
              <tbody>
                {documents.map(doc => (
                  <tr
                    className={cn(
                      'cursor-pointer border-t border-(--ui-stroke-tertiary) hover:bg-(--ui-control-hover-background)',
                      drawerDoc?.id === doc.id && 'bg-(--ui-control-active-background)'
                    )}
                    key={doc.id}
                    onClick={() => setDrawerDoc(doc)}
                  >
                    <td className="px-2 py-2" onClick={event => event.stopPropagation()}>
                      <Checkbox
                        checked={selected.has(doc.id)}
                        onCheckedChange={value => toggleOne(doc.id, value === true)}
                      />
                    </td>
                    <td className="max-w-0 truncate px-2 py-2 font-medium" title={doc.file_name}>
                      {doc.file_name}
                    </td>
                    <td className="px-2 py-2 text-muted-foreground">{doc.file_type || '—'}</td>
                    <td className="px-2 py-2 tabular-nums text-muted-foreground">{formatBytes(doc.file_size)}</td>
                    <td className="px-2 py-2">
                      <ParseStatusBadge status={doc.parse_status} />
                    </td>
                    <td className="px-2 py-2 text-center tabular-nums">{doc.chunk_count}</td>
                    <td className="px-2 py-2 text-muted-foreground">{formatKbDate(doc.created_at)}</td>
                    <td className="px-2 py-2" onClick={event => event.stopPropagation()}>
                      <Button onClick={() => setPendingDoc(doc)} size="xs" variant="text">
                        {t.common.delete}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {total > PAGE_SIZE ? (
          <div className="flex items-center justify-between gap-3 border-t border-(--ui-stroke-tertiary) px-4 py-2 text-xs text-muted-foreground">
            <span>{k.rangeOf((page - 1) * PAGE_SIZE + 1, Math.min(total, page * PAGE_SIZE), total)}</span>
            <div className="flex gap-2">
              <Button disabled={page <= 1} onClick={() => setPage(page - 1)} size="xs" variant="ghost">
                {t.common.back}
              </Button>
              <Button disabled={page >= pageCount} onClick={() => setPage(page + 1)} size="xs" variant="ghost">
                {k.nextPage}
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      {drawerDoc ? (
        <KnowledgePipelineDrawer doc={drawerDoc} kbId={kbId} onClose={() => setDrawerDoc(null)} />
      ) : null}
      </div>

      <CreateFolderDialog
        kbId={kbId}
        onClose={() => setFolderOpen(false)}
        open={folderOpen}
        parentId={folderId}
      />

      <ConfirmDialog
        confirmLabel={t.common.delete}
        description={pendingDoc ? k.deleteDocConfirm(pendingDoc.file_name) : undefined}
        destructive
        onClose={() => setPendingDoc(null)}
        onConfirm={async () => {
          if (!pendingDoc) {
            return
          }

          await deleteKnowledgeDocument(kbId, pendingDoc.id)
          if (drawerDoc?.id === pendingDoc.id) {
            setDrawerDoc(null)
          }
          setSelected(prev => {
            const next = new Set(prev)
            next.delete(pendingDoc.id)
            return next
          })
          await queryClient.invalidateQueries({ queryKey: knowledgeKeys.all })
          notify({ kind: 'success', message: k.deleted })
        }}
        open={Boolean(pendingDoc)}
        title={t.common.delete}
      />

      <ConfirmDialog
        confirmLabel={t.common.delete}
        description={pendingFolder ? k.deleteFolderConfirm(pendingFolder.name) : undefined}
        destructive
        onClose={() => setPendingFolder(null)}
        onConfirm={async () => {
          if (!pendingFolder) {
            return
          }

          await deleteKnowledgeFolder(kbId, pendingFolder.id)

          if (folderId === pendingFolder.id) {
            onFolderChange(null)
          }

          await queryClient.invalidateQueries({ queryKey: knowledgeKeys.folders(kbId) })
          await queryClient.invalidateQueries({ queryKey: ['knowledge', 'docs', kbId] })
          notify({ kind: 'success', message: k.deleted })
        }}
        open={Boolean(pendingFolder)}
        title={t.common.delete}
      />

      <ConfirmDialog
        confirmLabel={t.common.delete}
        description={k.bulkDeleteConfirm}
        destructive
        onClose={() => setBulkDeleteOpen(false)}
        onConfirm={async () => {
          const ids = [...selected]

          if (ids.length === 0) {
            return
          }

          await bulkDeleteDocuments(kbId, ids)
          if (drawerDoc && ids.includes(drawerDoc.id)) {
            setDrawerDoc(null)
          }
          setSelected(new Set())
          await queryClient.invalidateQueries({ queryKey: knowledgeKeys.all })
          notify({ kind: 'success', message: k.deleted })
        }}
        open={bulkDeleteOpen}
        title={t.common.delete}
      />

      <KnowledgeLlmConfirm
        onClose={() => setBatchWikiOpen(false)}
        onConfirm={async () => {
          const ids = [...selected]

          if (ids.length === 0) {
            return
          }

          setBatchBusy(true)

          try {
            await startBulkWiki(kbId, { docIds: ids })
            setSelected(new Set())
            await queryClient.invalidateQueries({ queryKey: knowledgeKeys.all })
            notify({ kind: 'success', message: k.actionStarted })
            onJobsTab()
          } catch (err) {
            notifyError(err, k.actionFailed)
            throw err
          } finally {
            setBatchBusy(false)
          }
        }}
        open={batchWikiOpen}
      />
    </div>
  )
}

function PanelEmptyLocal() {
  const { t } = useI18n()
  const k = t.knowledge

  return (
    <div className="flex h-full flex-col items-center justify-center gap-1 px-6 text-center">
      <p className="text-sm font-medium">{k.noDocumentsTitle}</p>
      <p className="text-xs text-muted-foreground">{k.noDocumentsDesc}</p>
    </div>
  )
}

function FolderRow({
  active,
  depth,
  label,
  onClick,
  onDelete
}: {
  active: boolean
  depth: number
  label: string
  onClick: () => void
  onDelete?: () => void
}) {
  const { t } = useI18n()

  return (
    <div className="group flex items-center">
      <button
        className={cn(
          'min-w-0 flex-1 truncate rounded-md px-2 py-1 text-left text-xs transition-colors',
          active
            ? 'bg-(--ui-control-active-background) text-foreground'
            : 'text-(--ui-text-secondary) hover:bg-(--ui-control-hover-background) hover:text-foreground'
        )}
        onClick={onClick}
        style={{ paddingLeft: `${0.5 + depth * 0.7}rem` }}
        type="button"
      >
        {label}
      </button>
      {onDelete ? (
        <Button
          className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
          onClick={onDelete}
          size="xs"
          variant="text"
        >
          {t.common.delete}
        </Button>
      ) : null}
    </div>
  )
}

function CreateFolderDialog({
  kbId,
  onClose,
  open,
  parentId
}: {
  kbId: string
  onClose: () => void
  open: boolean
  parentId: null | string
}) {
  const { t } = useI18n()
  const k = t.knowledge
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()

    const trimmed = name.trim()

    if (!trimmed || busy) {
      return
    }

    setBusy(true)

    try {
      await createKnowledgeFolder(kbId, trimmed, parentId)
      await queryClient.invalidateQueries({ queryKey: knowledgeKeys.folders(kbId) })
      notify({ kind: 'success', message: k.created })
      setName('')
      onClose()
    } catch (err) {
      notifyError(err, k.failedCreate)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog onOpenChange={value => !value && !busy && onClose()} open={open}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{k.newFolder}</DialogTitle>
          <DialogDescription>{k.folderHint}</DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={handleSubmit}>
          <Field htmlFor="kb-folder-name" label={k.nameLabel}>
            <Input
              autoFocus
              id="kb-folder-name"
              onChange={event => setName(event.target.value)}
              placeholder={k.folderNamePlaceholder}
              value={name}
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
