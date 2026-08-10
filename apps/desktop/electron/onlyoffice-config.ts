/**
 * onlyoffice-config.ts
 *
 * Persistence seam for the four OnlyOffice DocumentServer connection env vars
 * (HERMES_OFFICE_DS_URL / JWT_SECRET / CALLBACK_HOST / PREVIEW_PORT). Storing
 * them in a desktop config file means the integration is configured once in
 * Settings and auto-injected into the backend child env on every spawn — no
 * manual `export` in the launching shell after install.
 *
 * Kept standalone (no `import 'electron'`): every function takes the target
 * file path as a parameter, so the read/write/merge logic unit-tests without an
 * Electron runtime. main.ts owns the electron-coupled half — the
 * userData/onlyoffice.json path — and injects it, the same split as
 * native-token-store.ts.
 *
 * Precedence is deliberate: a *saved* value wins over the inherited
 * `process.env` value (the Settings panel is the authoritative install-time
 * config; the shell env is only a fallback for the un-configured case). The
 * JWT secret is never echoed back to the renderer — the panel only learns
 * whether one is configured and re-types it to change it.
 */

import fs from 'fs'
import path from 'path'

export interface OnlyOfficeConfig {
  dsUrl?: string
  jwtSecret?: string
  callbackHost?: string
  previewPort?: string
}

/** camelCase config field → the env var name injected into the backend. */
export const ONLYOFFICE_ENV_KEYS = {
  dsUrl: 'HERMES_OFFICE_DS_URL',
  jwtSecret: 'HERMES_OFFICE_JWT_SECRET',
  callbackHost: 'HERMES_OFFICE_CALLBACK_HOST',
  previewPort: 'HERMES_OFFICE_PREVIEW_PORT'
} as const

export type OnlyOfficeConfigField = keyof typeof ONLYOFFICE_ENV_KEYS

const CONFIG_FIELDS: readonly OnlyOfficeConfigField[] = ['dsUrl', 'jwtSecret', 'callbackHost', 'previewPort']

/**
 * Parse + validate the config file. Returns null when the file is missing,
 * unreadable, or not a JSON object — never a partially-populated config.
 * Non-empty string fields are trimmed; everything else is dropped.
 */
export function readOnlyofficeConfig(filePath: string): OnlyOfficeConfig | null {
  let parsed: unknown

  try {
    parsed = JSON.parse(fs.readFileSync(filePath, 'utf8'))
  } catch {
    return null
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return null
  }

  const record = parsed as Record<string, unknown>
  const config: OnlyOfficeConfig = {}

  for (const field of CONFIG_FIELDS) {
    const value = record[field]

    if (typeof value === 'string' && value.trim()) {
      config[field] = value.trim()
    }
  }

  return config
}

/** Persist the config (an empty config clears the file). mkdir + write. */
export function writeOnlyofficeConfig(config: OnlyOfficeConfig, filePath: string): void {
  const payload: Record<string, string> = {}

  for (const field of CONFIG_FIELDS) {
    const value = config[field]

    if (typeof value === 'string' && value.trim()) {
      payload[field] = value.trim()
    }
  }

  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  fs.writeFileSync(filePath, JSON.stringify(payload, null, 2), 'utf8')
}

/**
 * The env map to merge into the backend spawn env: saved config value wins,
 * `processEnv` (the launching shell) falls back. Passed `undefined` values are
 * harmless — the existing spawn already passes them for unset keys.
 */
export function resolveOnlyOfficeEnv(
  config: OnlyOfficeConfig | null,
  processEnv: NodeJS.ProcessEnv
): Record<string, string | undefined> {
  const env: Record<string, string | undefined> = {}

  for (const field of CONFIG_FIELDS) {
    env[ONLYOFFICE_ENV_KEYS[field]] = config?.[field] || processEnv[ONLYOFFICE_ENV_KEYS[field]]
  }

  return env
}

export interface OnlyOfficeStatus {
  /** Both DS URL and JWT secret present → backend runs OnlyOffice mode. */
  enabled: boolean
  /** Where the effective values come from. */
  source: 'config' | 'env' | 'none'
  dsUrl?: string
  callbackHost?: string
  previewPort?: string
  jwtSecretConfigured: boolean
}

/** What the backend actually sees (config-wins-then-env), for the panel banner. */
export function onlyOfficeStatus(config: OnlyOfficeConfig | null, processEnv: NodeJS.ProcessEnv): OnlyOfficeStatus {
  const dsUrl = config?.dsUrl || processEnv[ONLYOFFICE_ENV_KEYS.dsUrl]
  const jwtSecret = config?.jwtSecret || processEnv[ONLYOFFICE_ENV_KEYS.jwtSecret]
  const callbackHost = config?.callbackHost || processEnv[ONLYOFFICE_ENV_KEYS.callbackHost]
  const previewPort = config?.previewPort || processEnv[ONLYOFFICE_ENV_KEYS.previewPort]

  let source: OnlyOfficeStatus['source'] = 'none'

  if (config && CONFIG_FIELDS.some(field => Boolean(config[field]))) {
    source = 'config'
  } else if (dsUrl || jwtSecret) {
    source = 'env'
  }

  return {
    enabled: Boolean(dsUrl && jwtSecret),
    source,
    dsUrl: dsUrl || undefined,
    callbackHost: callbackHost || undefined,
    previewPort: previewPort || undefined,
    jwtSecretConfigured: Boolean(jwtSecret)
  }
}

/**
 * The panel-facing slice of the SAVED config: everything except the secret
 * (which is never echoed back to the renderer) plus a configured flag.
 */
export function publicOnlyOfficeConfig(config: OnlyOfficeConfig | null): {
  dsUrl?: string
  callbackHost?: string
  previewPort?: string
  jwtSecretConfigured: boolean
} {
  return {
    dsUrl: config?.dsUrl,
    callbackHost: config?.callbackHost,
    previewPort: config?.previewPort,
    jwtSecretConfigured: Boolean(config?.jwtSecret)
  }
}

/** Light validation of panel input; returns a user-facing error or null. */
export function validateOnlyOfficeConfig(config: OnlyOfficeConfig): string | null {
  if (config.dsUrl && !/^https?:\/\//i.test(config.dsUrl)) {
    return 'DS URL must start with http:// or https://'
  }

  if (config.previewPort && !/^\d+$/.test(config.previewPort)) {
    return 'Preview port must be numeric'
  }

  return null
}
