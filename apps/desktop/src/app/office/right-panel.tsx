import { useI18n } from '@/i18n'

import { Ledger } from './ledger'

/**
 * 右侧面板：任务流水 + 快捷工具（MVP 占位）。从 Vue OfficeRightPanel 移植。
 */
export function RightPanel() {
  const { t } = useI18n()
  const o = t.office

  return (
    <div className="flex h-full min-h-0 w-72 shrink-0 flex-col border-l border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background)">
      <div className="min-h-0 flex-1">
        <Ledger />
      </div>
      <div className="shrink-0 border-t border-(--ui-stroke-tertiary) p-3">
        <span className="text-xs font-medium text-(--ui-text-primary)">{o.rightPanel.quickTools}</span>
        <p className="mt-1 text-[0.65rem] text-(--ui-text-tertiary)">{o.rightPanel.activityEmpty}</p>
      </div>
    </div>
  )
}
