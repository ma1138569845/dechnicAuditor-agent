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
 * A full-viewport click-catcher sits behind the pill in BOTH states so an
 * outside click dismisses it while the prompt box is still clickable (it is
 * stacked above the catcher). ESC dismisses as well.
 */
export function AiEditToolbar({ anchor, onDismiss, onSubmit }: AiEditToolbarProps) {
  const { t } = useI18n()
  const [prompting, setPrompting] = useState(false)
  const [prompt, setPrompt] = useState('')
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  // ESC closes in either state.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onDismiss()
      }
    }

    window.addEventListener('keydown', onKeyDown)

    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onDismiss])

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
    <>
      {/* Click-catcher: outside click dismisses (and the toolbar above it stays
          clickable because it stacks on a higher z-index). */}
      <div
        aria-hidden
        className="fixed inset-0 z-40"
        data-slot="ai-edit-toolbar-catcher"
        onClick={onDismiss}
      />
      <div
        className="fixed z-50"
        data-slot="ai-edit-toolbar"
        onClick={event => event.stopPropagation()}
        style={{ left: prompting ? boxX : anchor.x, top: prompting ? boxY : anchor.y }}
      >
        {prompting ? (
          <form
            className="flex w-80 items-end gap-1.5 rounded-full border border-border/60 bg-background p-2 shadow-lg"
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
              'flex items-center gap-1 rounded-full border border-border bg-background px-2.5 py-1 text-[0.625rem] font-bold shadow-lg transition-colors',
              'text-foreground hover:bg-accent'
            )}
            data-slot="ai-edit-open"
            onClick={() => setPrompting(true)}
            type="button"
          >
            <Pencil className="size-3" />
            {t.preview.aiEdit}
          </button>
        )}
      </div>
    </>
  )
}
