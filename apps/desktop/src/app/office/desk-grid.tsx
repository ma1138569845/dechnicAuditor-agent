import { useI18n } from '@/i18n'

import { avatarInitial } from './avatar-initial'
import { agentCssColor, agentTextCssColor } from './engine/theme'
import { StatusBadge } from './status-badge'

export interface OfficeGridProfile {
  name: string
  label?: string
  /** Messaging gateway up — secondary chip only. */
  online: boolean
  busy: boolean
  currentWork?: string | null
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

  return (
    <div className="h-full w-full overflow-y-auto bg-(--ui-bg-secondary) p-5">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(190px,1fr))] gap-4">
        {profiles.map(profile => {
          const display = profile.label?.trim() || profile.name
          return (
            <button
              className="flex cursor-pointer flex-col gap-2 rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-card) p-2.5 text-left transition-colors hover:border-(--ui-accent) focus-visible:border-(--ui-accent) focus-visible:outline-none"
              key={profile.name}
              onClick={event => onAgentClick({ name: profile.name, clientX: event.clientX, clientY: event.clientY })}
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
                    {avatarInitial(display)}
                  </div>
                  <div
                    className="absolute bottom-[10px] left-1/2 h-[26px] w-[36px] -translate-x-1/2 rounded-[10px_10px_6px_6px]"
                    style={{ background: agentCssColor(profile.name) }}
                  />
                </div>
              </div>
              <div className="flex min-w-0 flex-col gap-1.5">
                <span className="truncate text-[13px] font-semibold text-(--ui-text-primary)">{display}</span>
                <StatusBadge busy={profile.busy} gatewayRunning={profile.online} />
                {profile.busy && profile.currentWork ? (
                  <span className="truncate text-[0.68rem] text-(--ui-yellow)" title={profile.currentWork}>
                    {profile.currentWork}
                  </span>
                ) : null}
              </div>
            </button>
          )
        })}
      </div>
      {profiles.length === 0 ? (
        <p className="py-10 text-center text-xs text-(--ui-text-tertiary)">{t.office.ledger.empty}</p>
      ) : null}
    </div>
  )
}
