import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  type EnergyAuditDatabaseValues,
  type EnergyAuditSettingsResponse,
  getEnergyAuditSettings,
  resetEnergyAuditSettings,
  saveEnergyAuditSettings,
  testEnergyAuditConnection
} from '@/hermes'
import { useI18n } from '@/i18n'
import { AlertCircle, Check, Loader2, Network, RefreshCw } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { confirm } from '@/store/confirm'
import { notify, notifyError } from '@/store/notifications'
import { $settingsScopeProfile } from '@/store/settings-scope'

import { CONTROL_TEXT } from './constants'
import { ListRow, Pill, SettingsContent, SettingsSkeleton } from './primitives'

const EMPTY_VALUES: EnergyAuditDatabaseValues = {
  host: '',
  port: '5432',
  database: '',
  user: '',
  sslmode: 'prefer'
}

const SSL_MODES = ['disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full']

export function EnergyAuditSettings({ profile: profileOverride }: { profile?: null | string } = {}) {
  const { t } = useI18n()
  const copy = t.settings.energyAudit
  const scopedProfile = useStore($settingsScopeProfile)
  const profile = profileOverride === undefined ? scopedProfile : profileOverride
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<'save' | 'reset' | null>(null)
  const [testing, setTesting] = useState(false)
  const [values, setValues] = useState(EMPTY_VALUES)
  const [password, setPassword] = useState('')
  const [settings, setSettings] = useState<EnergyAuditSettingsResponse | null>(null)
  const [testMessage, setTestMessage] = useState('')
  const requestGeneration = useRef(0)
  const testGeneration = useRef(0)

  const accept = useCallback((next: EnergyAuditSettingsResponse) => {
    setSettings(next)
    setValues({ ...EMPTY_VALUES, ...next.values })
    setPassword('')
  }, [])

  useEffect(() => {
    const generation = ++requestGeneration.current
    setLoading(true)
    getEnergyAuditSettings(profile)
      .then(next => {
        if (generation === requestGeneration.current) {
          accept(next)
        }
      })
      .catch(error => {
        if (generation === requestGeneration.current) {
          notifyError(error, copy.failedLoad)
        }
      })
      .finally(() => {
        if (generation === requestGeneration.current) {
          setLoading(false)
        }
      })
  }, [accept, copy.failedLoad, profile])

  const save = async () => {
    const generation = ++requestGeneration.current
    setBusy('save')

    try {
      const next = await saveEnergyAuditSettings({ ...values, password }, profile)

      if (generation !== requestGeneration.current) {
        return
      }

      accept(next)
      notify({ kind: 'success', message: copy.savedMessage, title: copy.savedTitle })
    } catch (error) {
      notifyError(error, copy.saveFailed)
    } finally {
      if (generation === requestGeneration.current) {
        setBusy(null)
      }
    }
  }

  const test = async () => {
    const generation = ++testGeneration.current
    setTesting(true)
    setTestMessage('')

    try {
      const result = await testEnergyAuditConnection(profile)

      if (generation !== testGeneration.current) {
        return
      }

      setTestMessage(result.message)
      notify({
        kind: result.ok ? 'success' : 'error',
        message: result.message,
        title: result.ok ? copy.testOk : copy.testFailed
      })
    } catch (error) {
      notifyError(error, copy.testFailed)
    } finally {
      if (generation === testGeneration.current) {
        setTesting(false)
      }
    }
  }

  const reset = async () => {
    if (!(await confirm({ confirmLabel: copy.reset, destructive: true, title: copy.resetConfirm }))) {
      return
    }

    const generation = ++requestGeneration.current
    setBusy('reset')

    try {
      const next = await resetEnergyAuditSettings(profile)

      if (generation !== requestGeneration.current) {
        return
      }

      accept(next)
      notify({ kind: 'success', message: copy.resetMessage, title: copy.resetTitle })
    } catch (error) {
      notifyError(error, copy.resetFailed)
    } finally {
      if (generation === requestGeneration.current) {
        setBusy(null)
      }
    }
  }

  if (loading) {
    return <SettingsSkeleton sections={[{ rows: 6 }]} />
  }

  const source = (key: string) => (settings?.sources[key] ? copy.sourceLabel(settings.sources[key]) : undefined)

  const overrideDetail = (settings?.env_overrides ?? [])
    .map(key =>
      key === 'host'
        ? copy.hostTitle
        : key === 'port'
          ? copy.portTitle
          : key === 'database'
            ? copy.databaseTitle
            : key === 'user'
              ? copy.userTitle
              : copy.sslTitle
    )
    .join(copy.envOverrideSeparator)

  return (
    <SettingsContent>
      <div className="mb-5">
        <div className="flex items-center gap-2 text-[length:var(--conversation-text-font-size)] font-medium">
          <Network className="size-4 text-muted-foreground" />
          {copy.title}
          <Pill tone={settings?.password_set ? 'primary' : 'warn'}>
            {settings?.password_set ? <Check className="mr-1 inline size-3" /> : null}
            {settings?.password_set ? copy.passwordSet : copy.passwordMissing}
          </Pill>
        </div>
        <p className="mt-2 max-w-2xl text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)">
          {copy.intro}
        </p>
      </div>

      {settings?.env_overrides.length ? (
        <div className="mb-5 flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-[length:var(--conversation-caption-font-size)]">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <div>{copy.envOverride(overrideDetail)}</div>
        </div>
      ) : null}

      <div className="grid gap-1">
        {(
          [
            ['host', copy.hostTitle, copy.hostDesc],
            ['port', copy.portTitle, copy.portDesc],
            ['database', copy.databaseTitle, copy.databaseDesc],
            ['user', copy.userTitle, copy.userDesc]
          ] as const
        ).map(([key, title, description]) => (
          <ListRow
            action={
              <Input
                className={CONTROL_TEXT}
                onChange={event => setValues(current => ({ ...current, [key]: event.target.value }))}
                value={values[key]}
              />
            }
            description={description}
            hint={source(key)}
            key={key}
            title={title}
          />
        ))}
        <ListRow
          action={
            <Select onValueChange={sslmode => setValues(current => ({ ...current, sslmode }))} value={values.sslmode}>
              <SelectTrigger aria-label={copy.sslTitle} className={cn('min-w-36', CONTROL_TEXT)}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SSL_MODES.map(mode => (
                  <SelectItem key={mode} value={mode}>
                    {mode}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          }
          description={copy.sslDesc}
          hint={source('sslmode')}
          title={copy.sslTitle}
        />
        <ListRow
          action={
            <Input
              autoComplete="off"
              className={CONTROL_TEXT}
              onChange={event => setPassword(event.target.value)}
              placeholder={settings?.password_set ? copy.passwordSetPlaceholder : copy.passwordPlaceholder}
              type="password"
              value={password}
            />
          }
          description={copy.passwordDesc}
          hint={source('password')}
          title={copy.passwordTitle}
        />
      </div>

      {testMessage ? <p className="mt-4 text-sm text-(--ui-text-secondary)">{testMessage}</p> : null}

      <div className="mt-6 flex flex-wrap items-center justify-end gap-3">
        <Button className="mr-auto" disabled={busy !== null} onClick={() => void reset()} size="sm" variant="text">
          {busy === 'reset' ? <Loader2 className="animate-spin" /> : <RefreshCw />}
          {copy.reset}
        </Button>
        <Button disabled={testing} onClick={() => void test()} size="sm" variant="textStrong">
          {testing ? <Loader2 className="animate-spin" /> : null}
          {copy.test}
        </Button>
        <Button disabled={busy !== null} onClick={() => void save()} size="sm">
          {busy === 'save' ? <Loader2 className="animate-spin" /> : null}
          {copy.save}
        </Button>
      </div>
    </SettingsContent>
  )
}
