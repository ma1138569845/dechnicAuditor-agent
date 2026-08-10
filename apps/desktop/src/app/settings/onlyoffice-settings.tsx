import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/i18n'
import { AlertCircle, Check, FileText, Loader2, Trash2 } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { notify, notifyError } from '@/store/notifications'

import { CONTROL_TEXT } from './constants'
import { EmptyState, ListRow, Pill, SettingsContent, SettingsSkeleton } from './primitives'

interface OnlyOfficeForm {
  dsUrl: string
  jwtSecret: string
  callbackHost: string
  previewPort: string
}

const EMPTY_FORM: OnlyOfficeForm = { dsUrl: '', jwtSecret: '', callbackHost: '', previewPort: '' }

/**
 * OnlyOffice DocumentServer connection config (see electron/onlyoffice-config.ts).
 * Values are persisted to userData/onlyoffice.json and auto-injected into the
 * backend spawn env, so the integration is configured once here instead of via
 * shell env. The JWT secret is never echoed back from the main process — it
 * only reports whether one is configured, so the panel re-types it to change it.
 */
export function OnlyOfficeSettings() {
  const { t } = useI18n()
  const o = t.settings.onlyoffice
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [form, setForm] = useState<OnlyOfficeForm>(EMPTY_FORM)
  const [secretConfigured, setSecretConfigured] = useState(false)
  const [effective, setEffective] = useState<OnlyOfficeSettingsState['effective'] | null>(null)

  useEffect(() => {
    let cancelled = false
    const desktop = window.hermesDesktop

    if (!desktop?.settings?.onlyoffice) {
      setLoading(false)

      return () => void (cancelled = true)
    }

    setLoading(true)
    desktop.settings.onlyoffice
      .get()
      .then(state => {
        if (cancelled) {
          return
        }

        setForm({
          dsUrl: state.saved.dsUrl ?? '',
          jwtSecret: '',
          callbackHost: state.saved.callbackHost ?? '',
          previewPort: state.saved.previewPort ?? ''
        })
        setSecretConfigured(state.saved.jwtSecretConfigured)
        setEffective(state.effective)
      })
      .catch(err => notifyError(err, o.failedLoad))
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => void (cancelled = true)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on mount; i18n copy is stable
  }, [])

  const acceptState = (state: OnlyOfficeSettingsState) => {
    setForm({
      dsUrl: state.saved.dsUrl ?? '',
      jwtSecret: '',
      callbackHost: state.saved.callbackHost ?? '',
      previewPort: state.saved.previewPort ?? ''
    })
    setSecretConfigured(state.saved.jwtSecretConfigured)
    setEffective(state.effective)
  }

  // An empty jwtSecret means "keep the stored one" (the panel never sees the
  // plaintext), so it is sent verbatim; the main side preserves it.
  const payload = (): OnlyOfficeConfigInput => ({
    dsUrl: form.dsUrl.trim(),
    jwtSecret: form.jwtSecret,
    callbackHost: form.callbackHost.trim(),
    previewPort: form.previewPort.trim()
  })

  const save = async (apply: boolean) => {
    setSaving(true)

    try {
      const next = apply
        ? await window.hermesDesktop.settings.onlyoffice.apply(payload())
        : await window.hermesDesktop.settings.onlyoffice.set(payload())

      acceptState(next)
      notify({
        kind: 'success',
        title: apply ? o.restartingTitle : o.savedTitle,
        message: apply ? o.restartingMessage : o.savedMessage
      })
    } catch (err) {
      notifyError(err, apply ? o.applyFailed : o.saveFailed)
    } finally {
      setSaving(false)
    }
  }

  const clear = async () => {
    setClearing(true)

    try {
      const next = await window.hermesDesktop.settings.onlyoffice.clear()
      acceptState(next)
      notify({ kind: 'success', title: o.clearedTitle, message: o.clearedMessage })
    } catch (err) {
      notifyError(err, o.clearFailed)
    } finally {
      setClearing(false)
    }
  }

  if (loading) {
    return <SettingsSkeleton sections={[{ rows: 4 }]} />
  }

  if (!window.hermesDesktop?.settings?.onlyoffice) {
    return <EmptyState description={o.unavailableDesc} title={o.unavailableTitle} />
  }

  const sourceLabel =
    effective?.source === 'config' ? o.sourceConfig : effective?.source === 'env' ? o.sourceEnv : null

  return (
    <SettingsContent>
      <div className="mb-5">
        <div className="flex items-center gap-2 text-[length:var(--conversation-text-font-size)] font-medium">
          <FileText className="size-4 text-muted-foreground" />
          {o.title}
          {effective?.enabled ? (
            <Pill tone="primary">
              <Check className="mr-1 inline size-3" />
              {o.enabled}
            </Pill>
          ) : (
            <Pill tone="warn">{o.disabled}</Pill>
          )}
          {sourceLabel ? <span className="text-xs text-muted-foreground">{sourceLabel}</span> : null}
        </div>
        <p className="mt-2 max-w-2xl text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)">
          {o.intro}
        </p>
      </div>

      {!effective?.enabled ? (
        <div className="mb-5 flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-[length:var(--conversation-caption-font-size)] text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <div className="leading-5">{o.envNotice}</div>
        </div>
      ) : null}

      <div className="grid gap-1">
        <ListRow
          action={
            <Input
              className={cn('h-8 font-mono', CONTROL_TEXT)}
              onChange={event => setForm(current => ({ ...current, dsUrl: event.target.value }))}
              placeholder="http://10.10.2.55:8090"
              value={form.dsUrl}
            />
          }
          description={o.dsUrlDesc}
          title={o.dsUrlTitle}
        />
        <ListRow
          action={
            <Input
              autoComplete="off"
              className={cn('h-8 font-mono', CONTROL_TEXT)}
              onChange={event => setForm(current => ({ ...current, jwtSecret: event.target.value }))}
              placeholder={secretConfigured ? o.secretSetPlaceholder : o.secretPlaceholder}
              type="password"
              value={form.jwtSecret}
            />
          }
          description={o.secretDesc}
          hint={secretConfigured ? o.secretKeepHint : undefined}
          title={o.secretTitle}
        />
        <ListRow
          action={
            <Input
              className={cn('h-8 font-mono', CONTROL_TEXT)}
              onChange={event => setForm(current => ({ ...current, callbackHost: event.target.value }))}
              placeholder={o.callbackHostPlaceholder}
              value={form.callbackHost}
            />
          }
          description={o.callbackHostDesc}
          title={o.callbackHostTitle}
        />
        <ListRow
          action={
            <Input
              className={cn('h-8 font-mono', CONTROL_TEXT)}
              inputMode="numeric"
              onChange={event => setForm(current => ({ ...current, previewPort: event.target.value }))}
              placeholder={o.previewPortPlaceholder}
              value={form.previewPort}
            />
          }
          description={o.previewPortDesc}
          title={o.previewPortTitle}
        />
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-end gap-4">
        <Button
          className="mr-auto"
          disabled={clearing || saving}
          onClick={() => void clear()}
          size="sm"
          variant="text"
        >
          {clearing ? <Loader2 className="animate-spin" /> : <Trash2 />}
          {o.clear}
        </Button>
        <Button disabled={saving || clearing} onClick={() => void save(false)} size="sm" variant="textStrong">
          {o.save}
        </Button>
        <Button disabled={saving || clearing} onClick={() => void save(true)} size="sm">
          {saving ? <Loader2 className="animate-spin" /> : null}
          {o.saveAndRestart}
        </Button>
      </div>
      <p className="mt-2 text-right text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)">
        {o.restartHint}
      </p>
    </SettingsContent>
  )
}
