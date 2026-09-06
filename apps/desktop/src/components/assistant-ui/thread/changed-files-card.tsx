import { useStore } from '@nanostores/react'
import { type FC, useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import { useComposerScope } from '@/app/chat/composer/scope'
import { useSessionView } from '@/app/chat/session-view'
import { pickRevealLabel } from '@/app/right-sidebar/file-actions'
import { ARTIFACTS_ROUTE, navigateToWorkspacePage } from '@/app/routes'
import { deriveChangedFiles, formatChangedFileSize, isHtmlPath } from '@/components/assistant-ui/thread/changed-files'
import { WIDGET_SHELL_CLASS } from '@/components/chat/widget-shell'
import { FadeScroll } from '@/components/ui/fade-scroll'
import { FileTypeIcon } from '@/components/ui/file-type-icon'
import { useI18n } from '@/i18n'
import { isDesktopFsRemoteMode } from '@/lib/desktop-fs'
import { displayPath } from '@/lib/display-path'
import { ArrowUpRight, ChevronRight, FolderOpen, Globe } from '@/lib/icons'
import { normalizeOrLocalPreviewTarget } from '@/lib/local-preview'
import { cn } from '@/lib/utils'
import { revealFile } from '@/store/file-actions'
import { notifyError } from '@/store/notifications'
import { openPreview } from '@/store/preview'
import { revealReview } from '@/store/review'

import type { ChangedFile } from './changed-files'

// First screen is a 2×2 — the Cursor artifact grid. A turn that rewrites a
// dozen files still reads as one compact cluster; "view all" unfolds the rest.
const PREVIEW_COUNT = 4
const EXPANDED_MAX_HEIGHT = '18rem'

/**
 * Cursor-style artifact tiles closing out a settled assistant turn: a 2-column
 * grid of file cards. The main control opens that file in the right preview
 * rail (HTML renders live). A separate folder button reveals it in the OS
 * file manager when the backend is local. The footer lists the count and
 * jumps to the Artifacts page; Review still opens the diff pane (⌘G).
 *
 * Wears the shared `WIDGET_SHELL_CLASS` per card so each tile matches the
 * transcript's other inline widgets rather than inventing its own chrome.
 */
export const ChangedFilesCard: FC<{
  /** Structured Kanban artifact paths stamped on the assistant message. */
  extraPaths?: readonly string[]
  /** Optional preceding-user-message text (Kanban wake MEDIA lines). */
  extraTexts?: readonly string[]
  parts: readonly unknown[]
}> = ({ extraPaths, extraTexts, parts }) => {
  const { t } = useI18n()
  const copy = t.assistant.thread
  const files = useMemo(
    () => deriveChangedFiles(parts, extraTexts, extraPaths),
    [extraPaths, extraTexts, parts]
  )
  const [expanded, setExpanded] = useState(false)
  const navigate = useNavigate()
  // Review THIS surface's repo: a tile transcript pins the pane to the tile's
  // worktree; the primary passes null (follow the active session, as before).
  const view = useSessionView()
  const viewCwd = useStore(view.$cwd)
  const scopeCwd = view.kind === 'primary' ? null : viewCwd || null
  const composerScope = useComposerScope()

  const visible = expanded || files.length <= PREVIEW_COUNT ? files : files.slice(0, PREVIEW_COUNT)
  const grid = files.length > 1
  const canReveal = !isDesktopFsRemoteMode()

  const openFile = useCallback(
    async (file: ChangedFile) => {
      try {
        const preview = await normalizeOrLocalPreviewTarget(file.path, viewCwd || undefined)

        if (!preview) {
          notifyError(new Error(copy.openFileFailed), t.rightSidebar.previewUnavailable)

          return
        }

        // Tool-result source so HTML lands in rendered preview, not source peek.
        openPreview(preview, 'tool-result')
      } catch (error) {
        notifyError(error, t.rightSidebar.previewUnavailable)
      }
    },
    [copy.openFileFailed, t.rightSidebar.previewUnavailable, viewCwd]
  )

  const revealInFolder = useCallback(
    async (file: ChangedFile) => {
      try {
        const preview = await normalizeOrLocalPreviewTarget(file.path, viewCwd || undefined)
        const path = preview?.path

        if (!path) {
          notifyError(new Error(copy.revealFileFailed), copy.revealFileFailed)

          return
        }

        await revealFile(path)
      } catch (error) {
        notifyError(error, copy.revealFileFailed)
      }
    },
    [copy.revealFileFailed, viewCwd]
  )

  const onViewAll = () => {
    if (!expanded && files.length > PREVIEW_COUNT) {
      setExpanded(true)

      return
    }

    navigateToWorkspacePage(navigate, ARTIFACTS_ROUTE)
  }

  if (files.length === 0) {
    return null
  }

  const list = (
    <div className={cn(grid ? 'grid grid-cols-2 gap-2' : 'max-w-md')}>
      {visible.map(file => (
        <ChangedFileTile
          canReveal={canReveal}
          file={file}
          key={file.path}
          onOpen={() => void openFile(file)}
          onReveal={() => void revealInFolder(file)}
        />
      ))}
    </div>
  )

  return (
    <div className="mt-1.5" data-slot="aui_changed-files">
      {expanded && files.length > PREVIEW_COUNT ? (
        <FadeScroll className="min-w-0" maxHeight={EXPANDED_MAX_HEIGHT}>
          {list}
        </FadeScroll>
      ) : (
        list
      )}
      <div className="mt-2 flex items-center gap-2 text-[length:var(--conversation-tool-font-size)]">
        <button
          className="inline-flex min-w-0 cursor-pointer items-center gap-0.5 text-(--ui-text-tertiary) transition-colors hover:text-(--ui-text-primary)"
          onClick={onViewAll}
          type="button"
        >
          <span className="truncate">{copy.viewAllArtifacts(files.length)}</span>
          <ChevronRight className="size-3.5 shrink-0" />
        </button>
        <span className="min-w-0 flex-1" />
        <button
          className="shrink-0 cursor-pointer text-(--ui-text-tertiary) transition-colors hover:text-(--ui-text-primary)"
          onClick={() => revealReview(scopeCwd, composerScope.target)}
          type="button"
        >
          {copy.reviewChanges}
        </button>
      </div>
    </div>
  )
}

const ChangedFileTile: FC<{
  canReveal: boolean
  file: ChangedFile
  onOpen: () => void
  onReveal: () => void
}> = ({ canReveal, file, onOpen, onReveal }) => {
  const { t } = useI18n()
  const copy = t.assistant.thread
  const revealLabel = pickRevealLabel(t.fileMenu.revealFinder, t.fileMenu.revealExplorer, t.fileMenu.revealFileManager)
  const sizeLabel = formatChangedFileSize(file.byteSize)
  const html = isHtmlPath(file.path)
  const pathLabel = displayPath(file.path)

  return (
    <div className={cn(WIDGET_SHELL_CLASS, 'flex w-full items-stretch overflow-hidden text-left')}>
      <button
        aria-label={copy.openFilePreview(file.name)}
        className={cn(
          'flex min-w-0 flex-1 cursor-pointer items-start gap-2.5 py-2.5 pl-3 text-left',
          canReveal ? 'pr-1' : 'pr-3'
        )}
        onClick={onOpen}
        type="button"
      >
        <span className="grid size-8 shrink-0 place-items-center rounded-md bg-muted/55 text-muted-foreground">
          <FileTypeIcon path={file.path} size="0.95rem" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[length:var(--conversation-text-font-size)] font-medium text-foreground">
            {file.name}
          </span>
          <span className="block truncate text-[length:var(--conversation-tool-font-size)] text-muted-foreground">
            {sizeLabel || pathLabel}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1 pt-0.5 text-muted-foreground">
          {html && <Globe aria-hidden className="size-3.5" />}
          <ArrowUpRight aria-hidden className="size-3.5" />
        </span>
      </button>
      {canReveal ? (
        <button
          aria-label={revealLabel}
          className="flex shrink-0 cursor-pointer items-start py-2.5 pr-3 pl-1 text-muted-foreground transition-colors hover:text-foreground"
          onClick={onReveal}
          title={revealLabel}
          type="button"
        >
          <span className="rounded-md p-1 hover:bg-muted/55">
            <FolderOpen aria-hidden className="size-3.5" />
          </span>
        </button>
      ) : null}
    </div>
  )
}
