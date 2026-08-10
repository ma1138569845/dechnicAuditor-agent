// Real ONLYOFFICE DocumentServer E2E — edit a cell, Ctrl+S, verify disk.
//
// Loads the /onlyoffice shell in headless Chrome, waits for the DS editor to
// mount, types a value into the active cell (the DS cell-input textarea is
// focused on load), saves via the native DS Ctrl+S, waits for a FRESH save
// callback (saved_at changes), and verifies the on-disk xlsx now contains the
// edited value with the existing formula intact. Run from the repo root:
//
//   node tests/tools/e2e_onlyoffice_ds.mjs "<url>" "<abs xlsx path>" <file_id>
//
// Requires the Hermes backend to be up with HERMES_OFFICE_* set and the DS
// reachable at HERMES_OFFICE_DS_URL.

import { chromium } from 'playwright'
import fs from 'node:fs'
import { execFileSync } from 'node:child_process'

const [, , url, filePath, fileId] = process.argv
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const BASE = new URL(url).origin
const EDIT_VALUE = 'E2E-' + Date.now()

function log(...args) { console.log(new Date().toISOString().slice(11, 19), ...args) }

const before = fs.readFileSync(filePath)

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
})
const page = await browser.newPage()
const consoleErrors = []
const badResponses = []
page.on('console', (msg) => {
  if (msg.type() === 'error') {
    const loc = msg.location()
    consoleErrors.push(msg.text() + (loc && loc.url ? '  @' + loc.url : ''))
  }
})
page.on('pageerror', (err) => consoleErrors.push('pageerror: ' + err.message))
page.on('response', (res) => {
  if (res.status() >= 400) {
    badResponses.push({ status: res.status(), url: res.url() })
    log(`HTTP ${res.status()}:`, res.url().slice(0, 120))
  }
})

const saveState = async () => {
  const r = await page.request.get(`${BASE}/api/onlyoffice/status?file_id=${fileId}`)
  return r.ok() ? r.json() : null
}

log('navigating to', url)
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 })

// 1. DS editor mounts.
log('waiting for DS editor ready…')
await page.waitForSelector('#status[data-kind="ready"]', { timeout: 90000 })
log('EDITOR READY; title =', await page.textContent('#title'))
await page.waitForTimeout(5000)
const baseline = await saveState()
log('status baseline (before editing) =', JSON.stringify(baseline))

// 2. The DS spreadsheet editor focuses its cell-input textarea on load; type a
//    real value into the active cell and commit with Enter. To defeat focus
//    flakiness we wait for the textarea, force focus if needed, and verify the
//    keystrokes actually landed before pressing Enter.
const frame = page.frames().find((f) => f.url().includes('10.10.2.55'))
if (!frame) { console.error('FAIL: no DS editor frame'); await browser.close(); process.exit(1) }
log('DS frame =', frame.url().slice(0, 80))

// The DS spreadsheet cell-input box is the <textarea id="area_id">; there are
// other textareas (e.g. the comment box) so we must target it explicitly.
const readTextarea = () => frame.evaluate(() => {
  const ta = document.querySelector('textarea#area_id')
  const focused = document.activeElement
  const focusedTa = focused && focused.tagName === 'TEXTAREA' ? focused.id : null
  return ta
    ? { exists: true, focused: document.activeElement === ta, id: ta.id, value: ta.value, focusedTa }
    : { exists: false, focusedTa }
})
let ta = await readTextarea()
log('textarea#area_id initial =', JSON.stringify(ta))
if (!ta.exists) {
  await frame.waitForSelector('textarea#area_id', { timeout: 30000 })
  ta = await readTextarea()
}
if (ta.exists && !ta.focused) {
  // Click the grid so the active cell (and its input box) grabs focus.
  await frame.locator('body').click({ position: { x: 200, y: 200 } })
  await page.waitForTimeout(1000)
  ta = await readTextarea()
  log('textarea#area_id after grid click =', JSON.stringify(ta))
}

log('typing', EDIT_VALUE, 'into the active cell…')
await page.keyboard.type(EDIT_VALUE, { delay: 40 })
await page.waitForTimeout(300)
const landed = await readTextarea()
log('textarea after typing =', JSON.stringify({ id: landed.id, value: landed.value }))
if (!landed.value || !landed.value.includes(EDIT_VALUE.slice(0, 8))) {
  console.error('FAIL: keystrokes did not land in the cell input box')
  await browser.close()
  process.exit(1)
}
await page.keyboard.press('Enter')
await page.waitForTimeout(1500)

// 3. Save. With customization.forcesave the DS sends a status-6 callback
//    ~2s after the edit commits (the reliable path); Ctrl+S is belt-and-
//    suspenders. Either way we watch for saved_at to move off the baseline
//    taken before editing.
await frame.locator('body').click({ position: { x: 95, y: 130 } })
for (let i = 0; i < 3; i++) {
  await page.keyboard.press('Control+s')
  await page.waitForTimeout(500)
}
log('Ctrl+S sent (x3); waiting for a FRESH saved_at vs baseline…')

let fresh = null
const deadline = Date.now() + 90000
while (Date.now() < deadline) {
  await new Promise((r) => setTimeout(r, 3000))
  const s = await saveState()
  if (s && s.status === 'saved' && s.saved_at && s.saved_at !== (baseline && baseline.saved_at)) {
    fresh = s
    break
  }
}
if (!fresh) { console.error('FAIL: no fresh save callback within 90s'); await browser.close(); process.exit(1) }
log('FRESH SAVE OK; saved_at =', fresh.saved_at)

// 4. Disk content check via openpyxl — the value must be present and the
//    existing formula must survive the DS re-serialization.
const after = fs.readFileSync(filePath)
const changed = !after.equals(before)
let contentOK = false
let formulaOK = false
try {
  const out = execFileSync('D:/develop/anaconda3/python.exe',
    ['-c', `import json,openpyxl,sys; wb=openpyxl.load_workbook(sys.argv[1], data_only=False); ws=wb.active; vals=[str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]; print(json.dumps(vals)); print(ws['C2'].value)`, filePath],
    { encoding: 'utf8', timeout: 30000 })
  const lines = out.trim().split('\n')
  const vals = JSON.parse(lines[lines.length - 2] ?? '[]')
  const c2 = lines[lines.length - 1] ?? ''
  contentOK = vals.some((v) => v.startsWith('E2E-'))
  formulaOK = c2 === '=SUM(A2:B2)'
  log('cells on disk =', JSON.stringify(vals))
  log('C2 formula on disk =', c2)
} catch (e) {
  log('openpyxl read failed:', String(e.message || e).slice(0, 120))
}

log('disk bytes before =', before.length, 'after =', after.length, 'changed =', changed)
log('CONSOLE_ERRORS:', JSON.stringify(consoleErrors))
await browser.close()

if (!changed) { console.error('FAIL: disk bytes unchanged after fresh save'); process.exit(1) }
if (!contentOK) { console.error('FAIL: edited value not found on disk'); process.exit(1) }
if (!formulaOK) { console.error('FAIL: formula =SUM(A2:B2) not preserved'); process.exit(1) }
// Only fail on 4xx/5xx responses served by our own preview server origin —
// DS-internal asset 404s (fonts, favicon) are out of scope and harmless here.
const origin = new URL(BASE).origin
const integrationErrors = badResponses.filter(
  (r) => r.url.startsWith(origin) && !r.url.includes('favicon')
)
if (integrationErrors.length) {
  console.error('FAIL: preview-server HTTP errors:', integrationErrors)
  await browser.close()
  process.exit(1)
}
console.log('E2E OK')
