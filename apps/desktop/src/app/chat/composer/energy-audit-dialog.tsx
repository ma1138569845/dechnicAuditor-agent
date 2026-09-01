import { useCallback, useEffect, useRef, useState } from 'react'

import type { SubmitTextOptions } from '@/app/session/hooks/use-prompt-actions/utils'
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
import { energyAuditImitateSkillPrompt } from '@/lib/templates/energy-audit'
import { cn } from '@/lib/utils'
import { notifyError } from '@/store/notifications'
import { openPreview } from '@/store/preview'

const AUDIT_TYPES = ['公共机构', '公共建筑', '工业企业'] as const
const GENERATE_MODES = ['template', 'imitate'] as const
const EXECUTION_METHODS = ['script', 'agent'] as const

interface EnergyAuditDialogProps {
  open: boolean
  /** Audit type preselected from the clicked template chip. */
  defaultAuditType: string
  onOpenChange: (open: boolean) => void
  /** Submit a skill prompt into the current chat (智能体任务). */
  onSubmit?: (value: string, options?: SubmitTextOptions) => Promise<boolean> | boolean
}

export function EnergyAuditDialog({ open, defaultAuditType, onOpenChange, onSubmit }: EnergyAuditDialogProps) {
  const { t } = useI18n()
  const c = t.composer
  const c2 = c.energyAuditDialog

  const [unitName, setUnitName] = useState('')
  const [auditType, setAuditType] = useState(defaultAuditType)
  const [executionMethod, setExecutionMethod] = useState<(typeof EXECUTION_METHODS)[number]>('script')
  const [generateMode, setGenerateMode] = useState<(typeof GENERATE_MODES)[number]>('template')
  const [suggestions, setSuggestions] = useState<EnergyAuditProjectSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const searchTimerRef = useRef<number | undefined>(undefined)
  // Selecting a suggestion updates unitName and would otherwise re-open the list
  // via the search effect — skip the next auto-show in that case.
  const skipNextSuggestOpenRef = useRef(false)

  // Reset form state each time the dialog opens.
  useEffect(() => {
    if (open) {
      setAuditType(defaultAuditType)
      setExecutionMethod('script')
      setGenerateMode('template')
      setError(null)
      setGenerating(false)
      setShowSuggestions(false)
      skipNextSuggestOpenRef.current = false
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
          if (skipNextSuggestOpenRef.current) {
            skipNextSuggestOpenRef.current = false
            setShowSuggestions(false)
          } else {
            setShowSuggestions(result.projects.length > 0)
          }
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

    if (executionMethod === 'agent') {
      try {
        if (!onSubmit) {
          setError(c2.agentSubmitFailed)
          return
        }

        const accepted = await onSubmit(energyAuditImitateSkillPrompt(name, auditType))

        if (!accepted) {
          setError(c2.agentSubmitFailed)
          return
        }

        onOpenChange(false)
      } catch (err) {
        setError(c2.agentSubmitFailed)
        notifyError(err, c2.agentSubmitFailed)
      } finally {
        setGenerating(false)
      }

      return
    }

    try {
      const result = await generateEnergyAuditReport({
        project_name: name,
        audit_type: auditType,
        mode: generateMode
      })

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
      const timedOut = err instanceof Error && /timed out/i.test(err.message)
      const message = timedOut ? c2.generateTimeout : c2.generateFailed
      setError(message)
      notifyError(err, message)
    } finally {
      setGenerating(false)
    }
  }, [
    auditType,
    c2.agentSubmitFailed,
    c2.generateFailed,
    c2.generateTimeout,
    c2.unitRequired,
    executionMethod,
    generateMode,
    onOpenChange,
    onSubmit,
    unitName
  ])

  const handleSelectSuggestion = (suggestion: EnergyAuditProjectSearchResult) => {
    skipNextSuggestOpenRef.current = true
    setUnitName(suggestion.audited_name)
    setShowSuggestions(false)
  }

  const dismissSuggestions = useCallback(() => setShowSuggestions(false), [])

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
          <div className="grid gap-1.5">
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
            {searching && <span className="text-xs text-(--ui-text-tertiary)">{c2.searching}</span>}
            {showSuggestions && suggestions.length > 0 && (
              <ul
                aria-label={c2.projectSuggestions}
                className="max-h-40 overflow-auto rounded-md border border-border bg-background py-1 shadow-sm"
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
          </div>

          <div className="grid gap-1.5">
            <label className="text-xs font-medium text-(--ui-text-tertiary)" htmlFor="energy-audit-type">
              {c2.auditType}
            </label>
            <Select
              onOpenChange={open => {
                if (open) {
                  dismissSuggestions()
                }
              }}
              onValueChange={setAuditType}
              value={auditType}
            >
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

          <div className="grid gap-1.5">
            <label className="text-xs font-medium text-(--ui-text-tertiary)" htmlFor="energy-audit-execution">
              {c2.executionMethod}
            </label>
            <Select
              onOpenChange={open => {
                if (open) {
                  dismissSuggestions()
                }
              }}
              onValueChange={value => setExecutionMethod(value as (typeof EXECUTION_METHODS)[number])}
              value={executionMethod}
            >
              <SelectTrigger id="energy-audit-execution">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="script">{c2.executionMethodScript}</SelectItem>
                <SelectItem value="agent">{c2.executionMethodAgent}</SelectItem>
              </SelectContent>
            </Select>
            {executionMethod === 'agent' && (
              <p className="text-[0.7rem] leading-5 text-(--ui-text-tertiary)">{c2.executionMethodAgentHint}</p>
            )}
          </div>

          {executionMethod === 'script' && (
            <div className="grid gap-1.5">
              <label className="text-xs font-medium text-(--ui-text-tertiary)" htmlFor="energy-audit-mode">
                {c2.generateMode}
              </label>
              <Select
                onOpenChange={open => {
                  if (open) {
                    dismissSuggestions()
                  }
                }}
                onValueChange={value => setGenerateMode(value as (typeof GENERATE_MODES)[number])}
                value={generateMode}
              >
                <SelectTrigger id="energy-audit-mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="template">{c2.generateModeTemplate}</SelectItem>
                  <SelectItem value="imitate">{c2.generateModeImitate}</SelectItem>
                </SelectContent>
              </Select>
              {generateMode === 'imitate' && (
                <p className="text-[0.7rem] leading-5 text-(--ui-text-tertiary)">{c2.generateModeImitateHint}</p>
              )}
            </div>
          )}

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
              {generating
                ? executionMethod === 'agent'
                  ? c2.submittingAgentTask
                  : generateMode === 'imitate'
                    ? c2.generatingImitate
                    : c2.generating
                : executionMethod === 'agent'
                  ? c2.startAgentTask
                  : c2.generate}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
