import { type FormEvent, useEffect, useRef, useState } from 'react'

import { Codicon } from '@/components/ui/codicon'
import { useI18n } from '@/i18n'
import { Pencil } from '@/lib/icons'
import { cn } from '@/lib/utils'

import { PRIMARY_ICON_BTN } from '../composer/controls'

/** Viewport-space anchor for the floating toolbar — the top-left of the user's
 *  selection rect (or the mouse position on a bare gutter line pick). */
export interface AiEditToolbarAnchor {
  x: number
  y: number
}

interface AiEditToolbarProps {
  /** Where to pin the toolbar (viewport coordinates; the pane is `position:
   *  static`-relative, so fixed/absolute can't be shared without a ref). */
  anchor: AiEditToolbarAnchor
  /** Close the toolbar (outside click / ESC). */
  onDismiss: () => void
  /** Called with the prompt-box state whenever it opens/closes (and with
   *  `false` on unmount). The parent uses it so an empty selection report does
   *  not dismiss the toolbar while the user is composing a prompt. */
  onPromptingChange?: (open: boolean) => void
  /** User hit the send button with a non-empty prompt. */
  onSubmit: (prompt: string) => void
}

/**
 * Floating "AI edit" affordance on top of a source preview selection.
 *
 * Two states:
 *  - `collapsed` — a rounded "AI edit" pill so the selection never covers the
 *    chrome. Clicking it opens the prompt box.
 *  - `prompting` — a minimal single-row input mirroring the composer's chrome:
 *    a clean surface, a borderless textarea, and a round foreground send button
 *    on the right (the composer's `PRIMARY_ICON_BTN`). The ✓ hands the typed
 *    prompt to the caller to inject into the composer.
 *
 * ESC or an outside mousedown dismisses in either state. The pill reports its
 * prompt-box state to the parent via onPromptingChange so an empty selection
 * report from the editor only dismisses while the pill is collapsed.
 */
export function AiEditToolbar({ anchor, onDismiss, onPromptingChange, onSubmit }: AiEditToolbarProps) {
  const { t } = useI18n()
  const [prompting, setPrompting] = useState(false)
  const [prompt, setPrompt] = useState('')
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const rootRef = useRef<HTMLDivElement | null>(null)

  // ESC closes in either state. Outside clicks dismiss via a document-level
  // mousedown listener instead of a full-viewport click-catcher: a catcher
  // would sit above the OnlyOffice editor iframe and swallow right-clicks,
  // hiding the editor's own context menu. Clicks inside a cross-origin editor
  // iframe never bubble to this document, so those dismiss through the
  // selection-report flow (empty selection → onAiEditSelection(null)) instead.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onDismiss()
      }
    }

    const onMouseDown = (event: MouseEvent) => {
      const target = event.target as Node
      if (rootRef.current && !rootRef.current.contains(target)) {
        onDismiss()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('mousedown', onMouseDown)

    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('mousedown', onMouseDown)
    }
  }, [onDismiss])

  // Tell the parent whether the prompt box is open so it can keep the toolbar
  // alive against empty selection reports while the user is composing. Reset to
  // false on unmount (dismissal) so the parent never keeps a stale latch.
  useEffect(() => {
    onPromptingChange?.(prompting)
    return () => onPromptingChange?.(false)
  }, [onPromptingChange, prompting])

  // Focus the textarea when the prompt box opens.
  useEffect(() => {
    if (prompting) {
      inputRef.current?.focus()
    }
  }, [prompting])

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = prompt.trim()

    if (!trimmed) {
      return
    }

    onSubmit(trimmed)
  }

  // The prompt box is wider (and taller) than the collapsed pill, so clamp it
  // back on-screen when the selection sits near the viewport's right/bottom
  // edge. The pill itself stays exactly at the anchor.
  const boxX = Math.min(anchor.x, Math.max(0, window.innerWidth - 324))
  const boxY = Math.min(anchor.y, Math.max(0, window.innerHeight - 64))

  return (
    <div
      ref={rootRef}
      className="fixed z-50"
      data-slot="ai-edit-toolbar"
      onContextMenu={event => event.preventDefault()}
      style={{ left: prompting ? boxX : anchor.x, top: prompting ? boxY : anchor.y }}
    >
      {prompting ? (
        <form
          className="flex w-80 items-end gap-1.5 rounded-full border border-primary/60 bg-background p-2 pl-3 shadow-lg"
          data-slot="ai-edit-prompt-form"
          onSubmit={handleSubmit}
        >
          <textarea
            autoFocus
            className="max-h-44 min-h-10 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/60"
            data-slot="ai-edit-prompt-input"
            onChange={event => setPrompt(event.target.value)}
            placeholder={t.preview.aiEditHint}
            ref={inputRef}
            value={prompt}
          />
          <button
            aria-label={t.preview.aiEditConfirm}
            className={cn(PRIMARY_ICON_BTN, 'flex shrink-0 items-center justify-center')}
            data-slot="ai-edit-confirm"
            disabled={!prompt.trim()}
            title={t.preview.aiEditConfirm}
            type="submit"
          >
            <Codicon name="arrow-up" size="0.875rem" />
          </button>
        </form>
      ) : (
        <button
          className={cn(
            'flex items-center gap-2 rounded-full py-1.5 pl-1.5 pr-3.5 text-xs font-semibold',
            'border border-primary bg-primary text-primary-foreground shadow-lg',
            'transition-all hover:brightness-95 active:scale-[0.98]'
          )}
          data-slot="ai-edit-open"
          onClick={() => setPrompting(true)}
          type="button"
        >
          <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary-foreground text-primary shadow-sm">
            <Pencil className="size-3" />
          </span>
          {t.preview.aiEdit}
        </button>
      )}
    </div>
  )
}
