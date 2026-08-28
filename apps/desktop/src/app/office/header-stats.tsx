import { useI18n } from '@/i18n'

export interface OfficeStats {
  online: number
  busy: number
  openTasks: number
  doneToday: number
}

/**
 * 4 stat cards at the top of the virtual office page (online / busy / open
 * tasks / done today). Renders zeros while data is loading.
 */
export function HeaderStats({ stats }: { stats: OfficeStats | null }) {
  const { t } = useI18n()
  const o = t.office
  const s = stats ?? { online: 0, busy: 0, openTasks: 0, doneToday: 0 }

  const tiles = [
    { label: o.stats.online, value: s.online },
    { label: o.stats.busy, value: s.busy },
    { label: o.stats.openTasks, value: s.openTasks },
    { label: o.stats.doneToday, value: s.doneToday }
  ]

  return (
    <div className="flex shrink-0 flex-wrap gap-2 px-6 pt-4">
      {tiles.map(tile => (
        <div
          className="flex min-w-28 flex-1 flex-col gap-0.5 rounded-md border border-(--ui-stroke-tertiary) px-3.5 py-2"
          key={tile.label}
        >
          <span className="text-lg font-medium tabular-nums tracking-tight">{tile.value}</span>
          <span className="text-[0.65rem] text-(--ui-text-tertiary)">{tile.label}</span>
        </div>
      ))}
    </div>
  )
}
