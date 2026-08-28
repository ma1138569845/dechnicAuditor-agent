import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'

import { OFFICE_GLASS } from './chrome'

export interface OfficeStats {
  online: number
  busy: number
  openTasks: number
  doneToday: number
}

/**
 * Floating glass stats strip over the office scene.
 */
export function HeaderStats({
  onRefresh,
  refreshing,
  stats
}: {
  stats: OfficeStats | null
  onRefresh?: () => void
  refreshing?: boolean
}) {
  const { t } = useI18n()
  const o = t.office
  const s = stats ?? { online: 0, busy: 0, openTasks: 0, doneToday: 0 }

  const tiles = [
    {
      label: o.stats.online,
      value: s.online,
      valueClass: 'text-(--ui-green)',
      hint: o.status.hintIdle
    },
    {
      label: o.stats.busy,
      value: s.busy,
      valueClass: 'text-(--ui-yellow)',
      hint: o.status.hintBusy
    },
    {
      label: o.stats.openTasks,
      value: s.openTasks,
      valueClass: 'text-(--ui-text-primary)',
      hint: undefined
    },
    {
      label: o.stats.doneToday,
      value: s.doneToday,
      valueClass: 'text-(--ui-text-primary)',
      hint: undefined
    }
  ]

  return (
    <div className={`inline-flex w-max max-w-full items-center gap-1.5 rounded-2xl px-2 py-1.5 ${OFFICE_GLASS}`}>
      <div className="flex min-w-0 items-stretch">
        {tiles.map((tile, index) => (
          <div
            className={`flex min-w-14 flex-col justify-center gap-0.5 px-2.5 ${
              index > 0 ? 'border-s border-[color-mix(in_srgb,var(--ui-stroke-tertiary)_45%,transparent)]' : ''
            }`}
            key={tile.label}
            title={tile.hint}
          >
            <span className={`text-base font-medium tabular-nums tracking-tight ${tile.valueClass}`}>
              {tile.value}
            </span>
            <span className="text-[0.62rem] leading-none text-(--ui-text-tertiary)">{tile.label}</span>
          </div>
        ))}
      </div>
      {onRefresh ? (
        <Button
          className="me-0.5 self-center border-transparent bg-[color-mix(in_srgb,var(--ui-bg-elevated)_28%,transparent)] hover:bg-[color-mix(in_srgb,var(--ui-bg-elevated)_48%,transparent)]"
          disabled={refreshing}
          onClick={onRefresh}
          size="sm"
          variant="secondary"
        >
          {o.refresh}
        </Button>
      ) : null}
    </div>
  )
}
