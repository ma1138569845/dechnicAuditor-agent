import { useNavigate } from 'react-router'
import { useStore } from '@nanostores/react'

import { ARTIFACTS_ROUTE, KNOWLEDGE_ROUTE } from '@/app/routes'
import { Codicon } from '@/components/ui/codicon'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'

import { $officeActivity } from './activity'
import { OFFICE_GLASS, OFFICE_PANEL_W } from './chrome'
import { Ledger } from './ledger'

function formatActivityTime(at: number): string {
  try {
    return new Date(at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

/**
 * 右上角侧栏：默认收起为小按钮，展开后显示任务流水 / 快捷工具 / 动态。
 */
export function RightPanel({
  open,
  onOpenChange
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useI18n()
  const o = t.office
  const navigate = useNavigate()
  const activity = useStore($officeActivity)

  if (!open) {
    return (
      <button
        aria-expanded={false}
        aria-label={`${t.common.expand} ${o.ledger.title}`}
        className={`pointer-events-auto flex size-10 items-center justify-center rounded-xl text-(--ui-text-primary) transition-colors hover:bg-[color-mix(in_srgb,var(--ui-bg-elevated)_40%,transparent)] ${OFFICE_GLASS}`}
        onClick={() => onOpenChange(true)}
        type="button"
      >
        <Codicon name="list-unordered" size="1.05rem" />
      </button>
    )
  }

  return (
    <aside
      className={`flex max-h-full min-h-0 ${OFFICE_PANEL_W} shrink-0 flex-col overflow-hidden rounded-[1.25rem] ${OFFICE_GLASS}`}
    >
      <div className="flex shrink-0 items-center gap-1 border-b border-[color-mix(in_srgb,var(--ui-stroke-tertiary)_55%,transparent)] px-2.5 py-1.5">
        <span className="min-w-0 flex-1 truncate px-1 text-xs font-medium text-(--ui-text-primary)">
          {o.ledger.title}
        </span>
        <button
          aria-expanded={true}
          aria-label={`${t.common.collapse} ${o.ledger.title}`}
          className="grid size-7 place-items-center rounded-lg text-(--ui-text-tertiary) transition-colors hover:bg-(--ui-control-hover-background) hover:text-(--ui-text-primary)"
          onClick={() => onOpenChange(false)}
          type="button"
        >
          <Codicon name="chevron-right" size="0.9rem" />
        </button>
      </div>
      <div className="min-h-0 max-h-44 shrink overflow-hidden">
        <Ledger hideTitle />
      </div>
      <div className="shrink-0 space-y-2.5 border-t border-[color-mix(in_srgb,var(--ui-stroke-tertiary)_55%,transparent)] px-3 py-2.5">
        <div>
          <span className="text-[0.65rem] font-medium uppercase tracking-wide text-(--ui-text-tertiary)">
            {o.rightPanel.quickTools}
          </span>
          <div className="mt-1.5 flex gap-1.5">
            <Button
              className="flex-1 border-transparent bg-[color-mix(in_srgb,var(--ui-bg-elevated)_28%,transparent)] hover:bg-[color-mix(in_srgb,var(--ui-bg-elevated)_48%,transparent)]"
              onClick={() => void navigate(ARTIFACTS_ROUTE)}
              size="sm"
              variant="secondary"
            >
              {o.rightPanel.files}
            </Button>
            <Button
              className="flex-1 border-transparent bg-[color-mix(in_srgb,var(--ui-bg-elevated)_28%,transparent)] hover:bg-[color-mix(in_srgb,var(--ui-bg-elevated)_48%,transparent)]"
              onClick={() => void navigate(KNOWLEDGE_ROUTE)}
              size="sm"
              variant="secondary"
            >
              {t.sidebar.nav.knowledge}
            </Button>
          </div>
        </div>
        <div>
          <span className="text-[0.65rem] font-medium uppercase tracking-wide text-(--ui-text-tertiary)">
            {o.rightPanel.activity}
          </span>
          {activity.length === 0 ? (
            <p className="mt-1 text-[0.65rem] leading-relaxed text-(--ui-text-tertiary)">
              {o.rightPanel.activityEmpty}
            </p>
          ) : (
            <ul className="mt-1 flex max-h-20 flex-col gap-1 overflow-y-auto">
              {activity.map(item => (
                <li className="flex gap-2 text-[0.65rem] leading-snug" key={item.id}>
                  <span className="shrink-0 tabular-nums text-(--ui-text-tertiary)">
                    {formatActivityTime(item.at)}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-(--ui-text-secondary)">{item.summary}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </aside>
  )
}
