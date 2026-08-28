import { useI18n } from '@/i18n'

import { agentCssColor, agentTextCssColor } from './engine/theme'

export interface OfficeGridProfile {
  name: string
  online: boolean
  busy: boolean
}

// Ported from hermes-studio-vue `OfficeDeskGrid.vue` — DOM fallback shown when
// the Pixi scene cannot start. Styling remapped to the desktop app's tokens.
export function DeskGrid({
  onAgentClick,
  profiles
}: {
  profiles: OfficeGridProfile[]
  onAgentClick: (payload: { name: string; clientX: number; clientY: number }) => void
}) {
  const { t } = useI18n()
  const o = t.office

  const statusKey = (p: OfficeGridProfile): 'busy' | 'online' | 'offline' =>
    p.busy ? 'busy' : p.online ? 'online' : 'offline'
  const label = (p: OfficeGridProfile): string => o.status[statusKey(p)]

  return (
    <div className="h-full w-full overflow-y-auto bg-(--ui-bg-secondary) p-5">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(190px,1fr))] gap-4">
        {profiles.map(profile => {
          const key = statusKey(profile)
          return (
            <button
              className="flex cursor-pointer flex-col gap-2 rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-card) p-2.5 text-left transition-colors hover:border-(--ui-accent) focus-visible:border-(--ui-accent) focus-visible:outline-none"
              key={profile.name}
              onClick={event => onAgentClick({ name: profile.name, clientX: event.clientX, clientY: event.clientY })}
              style={{ opacity: key === 'offline' ? 0.6 : undefined }}
              type="button"
            >
              <div className="relative flex h-[76px] items-end justify-center border-b-2 border-(--ui-stroke-tertiary)">
                <div className="absolute left-1/2 top-0.5 h-[34px] w-[52px] -translate-x-1/2 rounded border-2 border-(--ui-text-secondary) bg-(--ui-bg-primary)" />
                <div className="relative h-[58px] w-[48px]">
                  <div className="absolute bottom-0 left-1/2 h-[14px] w-[30px] -translate-x-1/2 rounded-[5px] bg-(--ui-text-tertiary)" />
                  <div
                    className="absolute top-0 left-1/2 flex h-[34px] w-[34px] -translate-x-1/2 items-center justify-center rounded-full text-[15px] font-bold"
                    style={{ background: agentCssColor(profile.name), color: agentTextCssColor(profile.name) }}
                  >
                    {(profile.name || '?').trim()[0]?.toUpperCase() ?? '?'}
                  </div>
                  <div
                    className="absolute bottom-[10px] left-1/2 h-[26px] w-[36px] -translate-x-1/2 rounded-[10px_10px_6px_6px]"
                    style={{ background: agentCssColor(profile.name) }}
                  />
                </div>
                <span
                  className={`absolute right-1.5 top-1 h-[10px] w-[10px] rounded-full border border-(--ui-bg-card) shadow-[0_0_0_1px_var(--ui-stroke-tertiary)] ${
                    key === 'online' ? 'bg-(--ui-green)' : key === 'busy' ? 'bg-(--ui-yellow)' : 'bg-transparent'
                  }`}
                  title={label(profile)}
                />
              </div>
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate text-[13px] font-semibold text-(--ui-text-primary)">{profile.name}</span>
                <span className="text-xs text-(--ui-text-tertiary)">{label(profile)}</span>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
