import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { generateEnergyAuditReport, searchEnergyAuditProjects, type EnergyAuditProjectSearchResult } from '@/hermes'
import { useI18n } from '@/i18n'
import { FileText } from '@/lib/icons'
import { normalizeOrLocalPreviewTarget } from '@/lib/local-preview'
import { cn } from '@/lib/utils'
import { openPreview } from '@/store/preview'
import { notifyError } from '@/store/notifications'

const AUDIT_TYPES = ['公共机构', '公共建筑', '工业企业'] as const

interface EnergyAuditDialogProps {
  open: boolean
  /** Audit type preselected from the clicked template chip. */
  defaultAuditType: string
  onOpenChange: (open: boolean) => void
}

export function EnergyAuditDialog({ open, defaultAuditType, onOpenChange }: EnergyAuditDialogProps) {
  const { t } = useI18n()
  const c = t.composer
  const c2 = c.energyAuditDialog

  const [unitName, setUnitName] = useState('')
  const [auditType, setAuditType] = useState(defaultAuditType)
  const [suggestions, setSuggestions] = useState<EnergyAuditProjectSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const searchTimerRef = useRef<number | undefined>(undefined)

  // Reset form state each time the dialog opens.
  useEffect(() => {
    if (open) {
      setAuditType(defaultAuditType)
      setError(null)
      setGenerating(false)
    }
  }, [open, defaultAuditType])

  // Debounced project-name search for the suggestion list.
  useEffect(() => {
    const keyword = unitName.trim()

    if (!keyword) {
      setSuggestions([])
      setShowSuggestions(false)

      return
    }

    window.clearTimeout(searchTimerRef.current)
    setSearching(true)

    searchTimerRef.current = window.setTimeout(async () => {
      try {
        const result = await searchEnergyAuditProjects(keyword)

        if (result.ok && result.projects) {
          setSuggestions(result.projects)
          setShowSuggestions(result.projects.length > 0)
        } else {
          setSuggestions([])
          setShowSuggestions(false)
        }
      } catch {
        setSuggestions([])
        setShowSuggestions(false)
      } finally {
        setSearching(false)
      }
    }, 300)

    return () => window.clearTimeout(searchTimerRef.current)
  }, [unitName])

  const handleSubmit = useCallback(async () => {
    const name = unitName.trim()

    if (!name) {
      setError(c2.unitRequired)
      return
    }

    setError(null)
    setGenerating(true)

    try {
      const result = await generateEnergyAuditReport({ project_name: name, audit_type: auditType })

      if (!result.ok || !result.file_path) {
        setError(result.message || result.error || c2.generateFailed)

        return
      }

      const preview = await normalizeOrLocalPreviewTarget(result.file_path)

      if (preview) {
        openPreview(preview, 'tool-result')
      }

      onOpenChange(false)
    } catch (err) {
      notifyError(err, c2.generateFailed)
    } finally {
      setGenerating(false)
    }
  }, [auditType, c2.generateFailed, c2.unitRequired, onOpenChange, unitName])

  const handleSelectSuggestion = (suggestion: EnergyAuditProjectSearchResult) => {
    setUnitName(suggestion.audited_name)
    setShowSuggestions(false)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent bodyClassName="gap-5" className="max-w-md">
        <DialogHeader>
          <DialogTitle icon={FileText}>{c2.title}</DialogTitle>
          <DialogDescription>{c2.desc}</DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-4"
          onSubmit={e => {
            e.preventDefault()
            void handleSubmit()
          }}
        >
          <div className="relative grid gap-1.5">
            <label className="text-xs font-medium text-(--ui-text-tertiary)" htmlFor="energy-audit-unit">
              {c2.unitName}
            </label>
            <Input
              autoComplete="off"
              autoCorrect="off"
              id="energy-audit-unit"
              onChange={e => setUnitName(e.target.value)}
              onFocus={() => setShowSuggestions(suggestions.length > 0)}
              onKeyDown={e => {
                if (e.key === 'Escape') {
                  setShowSuggestions(false)
                }
              }}
              placeholder={c2.unitPlaceholder}
              spellCheck={false}
              value={unitName}
            />
            {showSuggestions && suggestions.length > 0 && (
              <ul
                aria-label={c2.projectSuggestions}
                className="absolute top-full z-50 mt-1 max-h-48 w-full overflow-auto rounded-md border border-border bg-(--ui-bg-primary) py-1 shadow-lg"
              >
                {suggestions.map(suggestion => (
                  <li key={suggestion.id}>
                    <button
                      className="flex w-full flex-col items-start gap-0.5 px-3 py-1.5 text-left hover:bg-(--ui-bg-tertiary)"
                      onClick={() => handleSelectSuggestion(suggestion)}
                      type="button"
                    >
                      <span className="text-xs font-medium text-foreground">{suggestion.audited_name}</span>
                      {suggestion.audit_year && (
                        <span className="text-[0.65rem] text-(--ui-text-tertiary)">{suggestion.audit_year}</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {searching && <span className="text-xs text-(--ui-text-tertiary)">{c2.searching}</span>}
          </div>

          <div className="grid gap-1.5">
            <label className="text-xs font-medium text-(--ui-text-tertiary)" htmlFor="energy-audit-type">
              {c2.auditType}
            </label>
            <Select onValueChange={setAuditType} value={auditType}>
              <SelectTrigger id="energy-audit-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AUDIT_TYPES.map(type => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {error && (
            <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              className={cn(generating && 'cursor-not-allowed opacity-60')}
              disabled={generating || !unitName.trim()}
              onClick={() => onOpenChange(false)}
              type="button"
              variant="ghost"
            >
              {t.common.cancel}
            </Button>
            <Button disabled={generating || !unitName.trim()} type="submit">
              {generating ? c2.generating : c2.generate}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
