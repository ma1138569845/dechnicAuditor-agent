import { useMemo } from 'react'
import { createPortal } from 'react-dom'

import { useI18n } from '@/i18n'

import { clampMenuPosition, MENU_MAX_HEIGHT, MENU_WIDTH } from './menu-position'

export interface AgentActionMenuProps {
  agentName: string
  /** Presentation label; falls back to agentName. */
  agentLabel?: string
  x: number
  y: number
  /** Other online profile names this agent can visit. */
  onlineTargets: string[]
  onClose: () => void
  onOpenProfile: (name: string) => void
  onInteract: (targetName: string) => void
}

/**
 * Floating action menu on agent click — visit another desk / view profile.
 * Cosmetic scene-only controls (manual state / emotes) were removed.
 */
export function AgentActionMenu({
  agentName,
  agentLabel,
  x,
  y,
  onlineTargets,
  onClose,
  onOpenProfile,
  onInteract
}: AgentActionMenuProps) {
  const { t } = useI18n()
  const a = t.office.actions
  const position = useMemo(
    () => clampMenuPosition(x, y, window.innerWidth, window.innerHeight),
    [x, y]
  )

  if (typeof document === 'undefined') return null

  return createPortal(
    <>
      <div aria-hidden className="fixed inset-0 z-50" onClick={onClose} />
      <div
        className="fixed z-50 max-h-[min(460px,calc(100vh-24px))] w-[220px] overflow-y-auto rounded-md border border-(--stroke-nous) bg-(--ui-bg-elevated) p-2 shadow-nous"
        data-testid="office-agent-action-menu"
        role="menu"
        style={{ left: position.left, top: position.top, width: MENU_WIDTH, maxHeight: MENU_MAX_HEIGHT }}
      >
        <div className="mb-2 flex items-center justify-between border-b border-(--ui-stroke-tertiary) px-2 pb-2.5 pt-1.5">
          <span className="text-sm font-bold text-(--ui-text-primary)">{agentLabel?.trim() || agentName}</span>
        </div>

        <div className="flex flex-col gap-1">
          <div className="px-2 pb-0.5 text-[11px] text-(--ui-text-tertiary)">{a.interact}</div>
          <div className="px-2 pb-1.5 text-[11px] leading-snug text-(--ui-text-secondary)">{a.interactHint}</div>
          {onlineTargets.map(name => (
            <button
              className="w-full rounded-md px-2.5 py-2 text-start text-[13px] text-(--ui-text-primary) hover:bg-(--ui-control-hover-background) focus-visible:bg-(--ui-control-hover-background) focus-visible:outline-none"
              key={name}
              onClick={() => {
                onInteract(name)
                onClose()
              }}
              role="menuitem"
              type="button"
            >
              {a.interactWith(name)}
            </button>
          ))}
          {onlineTargets.length === 0 ? (
            <div className="px-2 text-xs text-(--ui-text-tertiary)">{a.noOnlineTargets}</div>
          ) : null}
        </div>

        <div className="mt-2 flex flex-col gap-1 border-t border-(--ui-stroke-tertiary) pt-2">
          <button
            className="w-full rounded-md px-2.5 py-2 text-start text-[13px] text-(--ui-text-primary) hover:bg-(--ui-control-hover-background) focus-visible:bg-(--ui-control-hover-background) focus-visible:outline-none"
            data-testid="view-profile"
            onClick={() => {
              onOpenProfile(agentName)
              onClose()
            }}
            role="menuitem"
            type="button"
          >
            {a.viewProfile}
          </button>
        </div>
      </div>
    </>,
    document.body
  )
}
