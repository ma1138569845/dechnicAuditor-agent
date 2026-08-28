import { useI18n } from '@/i18n'

import { resolveOfficePresence, type OfficePresence } from './presence'

const TONE: Record<OfficePresence, { shell: string; dot: string; label: string; ring?: string }> = {
  idle: {
    shell:
      'bg-[color-mix(in_srgb,var(--ui-green)_16%,transparent)] border-[color-mix(in_srgb,var(--ui-green)_40%,transparent)]',
    dot: 'bg-(--ui-green)',
    label: 'text-[color-mix(in_srgb,var(--ui-green)_88%,var(--ui-text-primary))]'
  },
  busy: {
    shell:
      'bg-[color-mix(in_srgb,var(--ui-yellow)_18%,transparent)] border-[color-mix(in_srgb,var(--ui-yellow)_45%,transparent)]',
    dot: 'bg-(--ui-yellow)',
    label: 'text-[color-mix(in_srgb,var(--ui-yellow)_90%,var(--ui-text-primary))]',
    ring: 'animate-pulse'
  }
}

/**
 * Work-centric presence pill (空闲 / 忙碌).
 * Gateway-down is a secondary chip — not the main “offline” state.
 */
export function StatusBadge({
  busy,
  gatewayRunning,
  showHint = false
}: {
  busy: boolean
  /** Messaging gateway for this profile; false → secondary “网关未开”. */
  gatewayRunning?: boolean
  showHint?: boolean
}) {
  const { t } = useI18n()
  const presence = resolveOfficePresence(busy)
  const tone = TONE[presence]
  const label = presence === 'busy' ? t.office.status.busy : t.office.status.idle
  const hint = presence === 'busy' ? t.office.status.hintBusy : t.office.status.hintIdle
  const gatewayDown = gatewayRunning === false

  return (
    <span className="inline-flex max-w-full flex-col items-start gap-1" title={hint}>
      <span className="inline-flex flex-wrap items-center gap-1.5">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[0.7rem] font-semibold tracking-wide ${tone.shell} ${tone.label}`}
          data-testid="office-status-badge"
          data-state={presence}
        >
          <span className={`size-2 shrink-0 rounded-full ${tone.dot} ${tone.ring ?? ''}`} />
          {label}
        </span>
        {gatewayDown ? (
          <span
            className="inline-flex items-center rounded-full border border-[color-mix(in_srgb,var(--ui-stroke-tertiary)_70%,transparent)] bg-[color-mix(in_srgb,var(--ui-text-tertiary)_8%,transparent)] px-2 py-0.5 text-[0.62rem] text-(--ui-text-tertiary)"
            data-testid="office-gateway-chip"
            title={t.office.status.hintGatewayOff}
          >
            {t.office.status.gatewayOff}
          </span>
        ) : null}
      </span>
      {showHint ? (
        <span className="px-0.5 text-[0.62rem] leading-snug text-(--ui-text-tertiary)">
          {hint}
          {gatewayDown ? ` · ${t.office.status.hintGatewayOff}` : ''}
        </span>
      ) : null}
    </span>
  )
}
