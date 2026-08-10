/**
 * Tests for electron/onlyoffice-config.ts — the persistence + env-injection
 * seam for the OnlyOffice DocumentServer connection vars.
 *
 * The load-bearing contract this file guards: a *saved* value beats the
 * inherited shell env at spawn (the Settings panel is the authoritative
 * install-time config), and the JWT secret is never echoed back to the
 * renderer. Breaking either regresses "configure once, auto-applies".
 *
 * (Wired into the vitest `electron` project via electron/**\/*.test.ts.)
 */

import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, beforeEach, test } from 'vitest'

import {
  ONLYOFFICE_ENV_KEYS,
  publicOnlyOfficeConfig,
  onlyOfficeStatus,
  readOnlyofficeConfig,
  resolveOnlyOfficeEnv,
  validateOnlyOfficeConfig,
  writeOnlyofficeConfig
} from './onlyoffice-config'

let dir: string
let filePath: string

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'onlyoffice-config-'))
  filePath = path.join(dir, 'onlyoffice.json')
})

afterEach(() => {
  fs.rmSync(dir, { recursive: true, force: true })
})

test('write + read round-trips a populated config', () => {
  const config = {
    dsUrl: 'http://10.10.2.55:8090',
    jwtSecret: 's3cret',
    callbackHost: '192.168.0.238',
    previewPort: '39250'
  }

  writeOnlyofficeConfig(config, filePath)
  assert.deepEqual(readOnlyofficeConfig(filePath), config)
})

test('write trims whitespace and drops empty fields', () => {
  writeOnlyofficeConfig(
    { dsUrl: '  http://ds:8090  ', jwtSecret: '  ', callbackHost: '', previewPort: undefined },
    filePath
  )
  assert.deepEqual(readOnlyofficeConfig(filePath), { dsUrl: 'http://ds:8090' })
})

test('missing file reads as null', () => {
  assert.equal(readOnlyofficeConfig(filePath), null)
})

test('corrupt or non-object config reads as null', () => {
  fs.writeFileSync(filePath, 'not json', 'utf8')
  assert.equal(readOnlyofficeConfig(filePath), null)

  fs.writeFileSync(filePath, JSON.stringify([1, 2]), 'utf8')
  assert.equal(readOnlyofficeConfig(filePath), null)
})

test('non-string fields are dropped', () => {
  fs.writeFileSync(filePath, JSON.stringify({ dsUrl: 123, jwtSecret: { a: 1 } }), 'utf8')
  assert.deepEqual(readOnlyofficeConfig(filePath), {})
})

test('empty write clears the file', () => {
  writeOnlyofficeConfig({ dsUrl: 'http://ds:8090' }, filePath)
  writeOnlyofficeConfig({}, filePath)
  assert.deepEqual(readOnlyofficeConfig(filePath), {})
})

test('resolveOnlyOfficeEnv prefers saved config over process.env', () => {
  const env = {
    [ONLYOFFICE_ENV_KEYS.dsUrl]: 'http://shell:8090',
    [ONLYOFFICE_ENV_KEYS.jwtSecret]: 'shell-secret'
  }
  const merged = resolveOnlyOfficeEnv({ dsUrl: 'http://config:8090', jwtSecret: 'cfg-secret' }, env)

  assert.equal(merged[ONLYOFFICE_ENV_KEYS.dsUrl], 'http://config:8090')
  assert.equal(merged[ONLYOFFICE_ENV_KEYS.jwtSecret], 'cfg-secret')
})

test('resolveOnlyOfficeEnv falls back to process.env when config lacks a field', () => {
  const env = { [ONLYOFFICE_ENV_KEYS.dsUrl]: 'http://shell:8090' }
  const merged = resolveOnlyOfficeEnv({}, env)

  assert.equal(merged[ONLYOFFICE_ENV_KEYS.dsUrl], 'http://shell:8090')
  assert.equal(merged[ONLYOFFICE_ENV_KEYS.jwtSecret], undefined)
})

test('resolveOnlyOfficeEnv with null config preserves the old pass-through behavior', () => {
  const env = { [ONLYOFFICE_ENV_KEYS.dsUrl]: 'http://shell:8090', [ONLYOFFICE_ENV_KEYS.jwtSecret]: 's' }
  const merged = resolveOnlyOfficeEnv(null, env)

  assert.equal(merged[ONLYOFFICE_ENV_KEYS.dsUrl], 'http://shell:8090')
  assert.equal(merged[ONLYOFFICE_ENV_KEYS.jwtSecret], 's')
  assert.equal(merged[ONLYOFFICE_ENV_KEYS.callbackHost], undefined)
})

test('onlyOfficeStatus reports enabled + config source when both required fields are saved', () => {
  const status = onlyOfficeStatus({ dsUrl: 'http://ds:8090', jwtSecret: 's' }, {})

  assert.equal(status.enabled, true)
  assert.equal(status.source, 'config')
  assert.equal(status.jwtSecretConfigured, true)
  assert.equal(status.dsUrl, 'http://ds:8090')
})

test('onlyOfficeStatus reports env source when only the shell provides values', () => {
  const env = { [ONLYOFFICE_ENV_KEYS.dsUrl]: 'http://ds:8090', [ONLYOFFICE_ENV_KEYS.jwtSecret]: 's' }
  const status = onlyOfficeStatus(null, env)

  assert.equal(status.enabled, true)
  assert.equal(status.source, 'env')
})

test('onlyOfficeStatus is disabled when either required field is missing', () => {
  assert.equal(onlyOfficeStatus({ dsUrl: 'http://ds:8090' }, {}).enabled, false)
  assert.equal(onlyOfficeStatus({}, {}).enabled, false)
  assert.equal(onlyOfficeStatus(null, {}).enabled, false)
})

test('publicOnlyOfficeConfig never exposes the jwt secret', () => {
  const pub = publicOnlyOfficeConfig({ dsUrl: 'http://ds:8090', jwtSecret: 'top-secret', callbackHost: 'host' })

  assert.equal('jwtSecret' in pub, false)
  assert.equal(pub.jwtSecretConfigured, true)
  assert.equal(pub.dsUrl, 'http://ds:8090')
  assert.equal(pub.callbackHost, 'host')
})

test('validateOnlyOfficeConfig rejects bad DS URL and non-numeric port', () => {
  assert.match(validateOnlyOfficeConfig({ dsUrl: 'ftp://ds' })!, /http/)
  assert.match(validateOnlyOfficeConfig({ previewPort: 'abc' })!, /numeric/)
  assert.equal(validateOnlyOfficeConfig({ dsUrl: 'http://ds:8090' }), null)
  assert.equal(validateOnlyOfficeConfig({}), null)
})
