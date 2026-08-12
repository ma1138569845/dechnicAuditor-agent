/**
 * Skill-triggered template chips for the composer.
 *
 * Renders a horizontal strip of clickable template suggestions. Selecting a
 * chip replaces the composer contents with the template's prompt so the user
 * can review/edit before sending.
 */

import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'

export interface ComposerTemplate {
  id: string
  label: string
  description: string
  prompt: string
}

interface TemplateChipsProps {
  templates: ComposerTemplate[]
  title?: string
  onSelect: (template: ComposerTemplate) => void
  onClose?: () => void
}

export function TemplateChips({ templates, title, onSelect, onClose }: TemplateChipsProps) {
  const { t } = useI18n()

  return (
    <div
      className="flex flex-col gap-1.5 rounded-lg border border-[color-mix(in_srgb,var(--dt-composer-ring)_24%,transparent)] bg-(--ui-bg-tertiary)/60 px-2 py-1.5"
      data-slot="composer-template-chips"
    >
      <div className="flex items-center justify-between px-0.5">
        <span className="text-[0.65rem] font-medium uppercase tracking-wide text-(--ui-text-tertiary)">
          {title ?? t.composer.templateSuggestions ?? '模板'}
        </span>
        {onClose && (
          <button
            className="text-[0.65rem] text-(--ui-text-tertiary) transition-colors hover:text-foreground"
            onClick={onClose}
            type="button"
          >
            {t.common?.close ?? '关闭'}
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {templates.map(template => (
          <button
            className={cn(
              'group relative flex max-w-[14rem] items-center gap-1.5 rounded-md border border-border',
              'bg-(--ui-bg-primary) px-2 py-1 text-left transition-colors',
              'hover:border-primary hover:bg-(--ui-bg-primary)'
            )}
            key={template.id}
            onClick={() => onSelect(template)}
            title={template.description}
            type="button"
          >
            <span className="truncate text-xs font-medium text-foreground">{template.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
