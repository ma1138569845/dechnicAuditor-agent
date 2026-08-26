import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { useI18n } from '@/i18n'

export function KnowledgeLlmConfirm({
  onClose,
  onConfirm,
  open,
  variant = 'default'
}: {
  onClose: () => void
  onConfirm: (opts?: { curate?: boolean }) => Promise<void>
  open: boolean
  variant?: 'default' | 'wiki'
}) {
  const { t } = useI18n()
  const k = t.knowledge
  const [curate, setCurate] = useState(false)

  useEffect(() => {
    if (open) {
      setCurate(false)
    }
  }, [open])

  if (variant !== 'wiki') {
    return (
      <ConfirmDialog
        description={k.llmConfirmBody}
        onClose={onClose}
        onConfirm={() => onConfirm()}
        open={open}
        title={k.llmConfirmTitle}
      />
    )
  }

  return (
    <Dialog onOpenChange={value => !value && onClose()} open={open}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{k.wikiConfirmTitle}</DialogTitle>
          <DialogDescription>{k.wikiConfirmBody}</DialogDescription>
        </DialogHeader>
        <label className="flex cursor-pointer items-start gap-2.5 rounded-md border border-(--ui-stroke-tertiary) px-3 py-2.5">
          <Checkbox
            checked={curate}
            className="mt-0.5"
            onCheckedChange={value => setCurate(value === true)}
          />
          <span className="min-w-0">
            <span className="block text-xs font-medium text-foreground">{k.wikiCurateAfter}</span>
            <span className="mt-0.5 block text-[0.7rem] leading-relaxed text-muted-foreground">
              {k.wikiCurateAfterHint}
            </span>
          </span>
        </label>
        <DialogFooter>
          <Button onClick={onClose} type="button" variant="ghost">
            {t.common.cancel}
          </Button>
          <Button onClick={() => void onConfirm({ curate })} type="button">
            {k.generateWiki}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
