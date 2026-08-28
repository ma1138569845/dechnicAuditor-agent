import { useNavigate } from 'react-router'
import { useStore } from '@nanostores/react'

import { CRON_ROUTE } from '@/app/routes'
import { useI18n } from '@/i18n'

import { $cronJobs, $ledgerFilter, type LedgerFilter } from './store'

/**
 * 任务流水：cron 任务列表 + 过滤（全部/进行中/已完成）。
 * 数据源是桌面端的 cron jobs（Kanban 的 desktop 等价物）。
 * 行点击跳转到定时任务页。
 */
export function Ledger({ hideTitle = false }: { hideTitle?: boolean }) {
  const { t } = useI18n()
  const o = t.office
  const navigate = useNavigate()
  const filter = useStore($ledgerFilter)
  const jobs = useStore($cronJobs)

  const filtered = jobs.filter(job => {
    if (filter === 'open') return job.enabled
    if (filter === 'done') return !job.enabled
    return true
  })

  const filters: { id: LedgerFilter; label: string }[] = [
    { id: 'all', label: o.ledger.filterAll },
    { id: 'open', label: o.ledger.filterOpen },
    { id: 'done', label: o.ledger.filterDone }
  ]

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        className={`flex shrink-0 items-center gap-1 px-3 py-1.5 ${
          hideTitle ? '' : 'border-b border-(--ui-stroke-tertiary)/60'
        }`}
      >
        {hideTitle ? null : (
          <span className="text-xs font-medium text-(--ui-text-primary)">{o.ledger.title}</span>
        )}
        <div className={`${hideTitle ? '' : 'ml-auto'} flex gap-0.5 rounded-lg bg-(--ui-bg)/40 p-0.5`}>
          {filters.map(f => (
            <button
              className={`rounded-md px-2 py-0.5 text-[0.65rem] transition-colors ${
                filter === f.id
                  ? 'bg-(--ui-control-active-background) text-(--ui-text-primary) shadow-sm'
                  : 'text-(--ui-text-tertiary) hover:bg-(--ui-control-hover-background)/70 hover:text-(--ui-text-secondary)'
              }`}
              key={f.id}
              onClick={() => $ledgerFilter.set(f.id)}
              type="button"
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {filtered.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-(--ui-text-tertiary)">{o.ledger.empty}</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {filtered.map(job => (
              <li key={job.id}>
                <button
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-start text-xs hover:bg-(--ui-row-hover-background)/80 focus-visible:bg-(--ui-row-hover-background)/80 focus-visible:outline-none"
                  onClick={() => void navigate(CRON_ROUTE)}
                  type="button"
                >
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                      job.enabled ? 'bg-(--ui-green)' : 'bg-(--ui-text-tertiary)'
                    }`}
                  />
                  <span className="min-w-0 flex-1 truncate text-(--ui-text-primary)">{job.name || job.id}</span>
                  <span className="shrink-0 text-[0.65rem] tabular-nums text-(--ui-text-tertiary)">
                    {job.schedule_display || job.schedule?.display || ''}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
