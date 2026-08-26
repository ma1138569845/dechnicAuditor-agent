import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useI18n } from '@/i18n'

export function KnowledgeLlmConfirm({
  onClose,
  onConfirm,
  open
}: {
  onClose: () => void
  onConfirm: () => Promise<void>
  open: boolean
}) {
  const { t } = useI18n()
  const k = t.knowledge

  return (
    <ConfirmDialog
      description={k.llmConfirmBody}
      onClose={onClose}
      onConfirm={onConfirm}
      open={open}
      title={k.llmConfirmTitle}
    />
  )
}
