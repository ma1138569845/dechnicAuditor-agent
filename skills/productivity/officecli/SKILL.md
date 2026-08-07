---
name: officecli
description: Create, analyze, proofread, and modify Office documents (.docx, .xlsx, .pptx) using the officecli CLI tool. Use when the user wants to create, inspect, check formatting, find issues, add charts, or modify Office documents.
required_commands: [officecli]
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Office, DOCX, XLSX, PPTX, Productivity]
    category: productivity
    related_skills: [docx, xlsx, powerpoint]
---

# officecli

AI-friendly CLI for .docx, .xlsx, .pptx. Single binary, no dependencies, no Office installation needed.

## Install

If `officecli` is not installed:

```bash
# macOS / Linux
curl -fsSL https://d.officecli.ai/install.sh | bash

# Windows (PowerShell)
irm https://d.officecli.ai/install.ps1 | iex
```

Verify with `officecli --version`. If still not found after install, open a new terminal.

> **For skill authors:** see `references/required-commands-pattern.md` for why `required_commands` is declared in frontmatter — makes Hermes detect missing tools at load time rather than failing during execution.

---

## Strategy

**L1 (read) → L2 (DOM edit) → L3 (raw XML)**. Always prefer higher layers. Add `--json` for structured output.

**Before doc work, check Specialized Skills** (bottom of this file). Fundraising decks, academic papers, financial models, dashboards, and Morph animations need their own skill loaded first — `load_skill` once, then proceed.

---

## Help System (IMPORTANT)

**When unsure about property names, value formats, or command syntax, ALWAYS run help instead of guessing.** One help query beats guess-fail-retry loops.

`officecli help` ≡ `officecli --help`, and `officecli <cmd> --help` ≡ `officecli help <cmd>` — same content.

```bash
officecli help                                  # All commands + global options + schema entry points
officecli help docx                             # List all docx elements
officecli help docx paragraph                   # Full schema: properties, aliases, examples, readbacks
officecli help docx set paragraph               # Verb-filtered: only props usable with `set`
officecli help docx paragraph --json            # Structured schema (machine-readable)
```

Format aliases: `word`→`docx`, `excel`→`xlsx`, `ppt`/`powerpoint`→`pptx`. Verbs: `add`, `set`, `get`, `query`, `remove`. MCP exposes the same schema via the single `command` string param: `{"command":"help docx paragraph"}` (not a structured `{"format":...,"type":...}` object — the MCP tool has exactly one param, `command`, and passes it through to the CLI verbatim).

---

## Performance: Resident Mode

**Every command auto-starts a resident on first access** (60s idle timeout) — file-lock conflicts are automatically avoided. Explicit `open`/`close` is still recommended for longer sessions (12min idle):
```bash
officecli open report.docx       # explicitly keep in memory
officecli set report.docx ...    # no file I/O overhead
officecli close report.docx      # save and release
```

Opt out of auto-start: `OFFICECLI_NO_AUTO_RESIDENT=1`.

**Flush only at the non-officecli boundary.** officecli's own reads (`get`/`query`/`view`/`dump`) always see your latest edits, so you never need to save mid-workflow. Run `save` (keeps the resident) or `close` (flush + release) only **before a non-officecli program reads the file** — python-docx/openpyxl, Word, a renderer, delivery/upload. (Idle sessions auto-flush within seconds; `OFFICECLI_RESIDENT_FLUSH=each` makes every mutation flush before returning.)

---

## Quick Start

**PPT:**
```bash
officecli create slides.pptx
officecli add slides.pptx / --type slide --prop title="Q4 Report" --prop background=1A1A2E
officecli add slides.pptx '/slide[1]' --type shape --prop text="Revenue grew 25%" --prop x=2cm --prop y=5cm --prop font=Arial --prop size=24 --prop color=FFFFFF
```

**Word:**
```bash
officecli create report.docx
officecli add report.docx /body --type paragraph --prop text="Executive Summary" --prop style=Heading1
officecli add report.docx /body --type paragraph --prop text="Revenue increased by 25% year-over-year."
```

**Excel:**
```bash
officecli create data.xlsx
officecli set data.xlsx /Sheet1/A1 --prop value="Name" --prop bold=true
officecli set data.xlsx /Sheet1/A2 --prop value="Alice"
```

---

## L1: Create, Read & Inspect

```bash
officecli create <file>               # Create blank .docx/.xlsx/.pptx (type from extension)
officecli view <file> <mode>          # outline | stats | issues | text | annotated | html
officecli get <file> <path> --depth N # Get a node and its children [--json]
officecli query <file> <selector>     # CSS-like query
officecli validate <file>             # Validate against OpenXML schema
```

### view modes

| Mode | Description | Useful flags |
|------|-------------|-------------|
| `outline` | Document structure | |
| `stats` | Statistics (pages, words, shapes) | |
| `issues` | Formatting/content/structure problems | `--type format\|content\|structure`, `--limit N` |
| `text` | Plain text extraction | `--start N --end N`, `--max-lines N` |
| `annotated` | Text with formatting annotations | |
| `html` | Static HTML snapshot — same renderer as `watch`, no server needed | `--browser`, `--page N` (docx), `--start N --end N` (pptx) |
| `screenshot` / `svg` / `pdf` / `forms` | PNG via headless browser / SVG (pptx slide) / PDF via exporter plugin / form-fields JSON via format-handler plugin | `-o`, `--screenshot-width/-height`, pptx `--grid N` |

Use `view html` for one-shot snapshots (CI artifacts, archival, diffing); use `watch` when you need live refresh or browser-side click-to-select.

### get

Any XML path via element localName. Use `--depth N` to expand children. Add `--json` for structured output. Default text output is grep-friendly: `path (type) "text" key=val key=val ...`

```bash
officecli get report.docx '/body/p[3]' --depth 2 --json
officecli get slides.pptx '/slide[1]' --depth 1          # list all shapes on slide 1
officecli get data.xlsx '/Sheet1/B2' --json
```

### Stable ID Addressing

Elements with stable IDs return `@attr=value` paths instead of positional indices. Prefer these in multi-step workflows — positional indices shift on insert/delete, stable IDs do not.

```
/slide[1]/shape[@id=550950021]                    # PPT shape
/slide[1]/table[@id=1388430425]/tr[1]/tc[2]       # PPT table
/body/p[@paraId=1A2B3C4D]                         # Word paragraph
/comments/comment[@commentId=1]                    # Word comment
```

PPT also accepts `@name=` (e.g. `shape[@name=Title 1]`), with morph `!!` prefix awareness. Elements without stable IDs (slide, run, tr/tc, row) fall back to positional indices.

### query

CSS-like selectors: `[attr=value]`, `[attr!=value]`, `[attr~=text]`, `[attr>=value]`, `[attr<=value]`, `:contains("text")`, `:empty`, `:has(formula)`, `:no-alt`. Boolean `and`/`or` supported across `query`/`set`/`remove`: `cell[value>5000 or value<100]`, `cell[(type=Number or type=Date) and value>0]`. Excel row-by-column-name: `Sheet1!row[Salary>5000]`. `set` accepts selectors and Excel-native paths (parity with `get`/`query`). Bare unscoped selectors rejected on `set`/`remove`.

```bash
officecli query report.docx 'paragraph[style=Normal] > run[font!=Arial]'
officecli query slides.pptx 'shape[fill=FF0000]'
```

---

## Watch & Interactive Selection

Live HTML preview that auto-refreshes on every file change. Browsers can click / shift-click / box-drag to select shapes; the CLI can read the current browser selection and act on it.

```bash
officecli watch <file> [--port N]      # Start preview server (default port 26315)
officecli unwatch <file>               # Stop
officecli goto <file> <path>           # Scroll watching browser(s) to element (docx: p / table / tr / tc)
```

Open the printed `http://localhost:N` URL. Click to select; shift/cmd/ctrl+click to multi-select; drag from empty space to box-select. PPT/Word use blue outline; Excel uses native-style green selection (double-click cell to edit inline; drag a chart to reposition).

### `get <file> selected` — read what the user clicked

```bash
officecli get <file> selected [--json]
```

Returns DocumentNodes for whatever is currently selected. Empty result if nothing selected. Exit code != 0 if no watch is running.

```bash
# User clicks shapes in the browser, then asks "make these red"
PATHS=$(officecli get deck.pptx selected --json | jq -r '.data.Results[].path')
for p in $PATHS; do officecli set deck.pptx "$p" --prop fill=FF0000; done
```

### Key properties

- **Selection survives file edits.** Paths use stable `@id=` form.
- **All connected browsers share one selection.** Last-write-wins.
- **Same-file single-watch.** A given file can have only one watch process at a time.
- **Group shapes select as a whole.** Drilling into individual children of a group is not supported in v1.
- **Coverage:** `.pptx` shapes/pictures/tables/charts/connectors/groups; `.docx` top-level paragraphs and tables. Inherited layout/master decorations and Word nested elements (table cells, run-level) are not addressable. **`.xlsx` does not emit `data-path`** — `mark`/`selection` on xlsx always resolve `stale=true` (v2 candidate).

### Marks — edit proposals waiting for review

Use `mark` when changes need human review BEFORE they hit the file. Marks live in the watch process only; a separate `set` pipeline applies accepted ones. For one-shot changes use `set` directly; for permanent file annotations use `add --type comment` (Word native).

```bash
officecli mark <file> <path> [--prop find=... color=... note=... tofix=... regex=true] [--json]
officecli unmark <file> [--path <p> | --all] [--json]
officecli get-marks <file> [--json]
```

Props: `find` (literal or regex when `regex=true`; raw form `find='r"[abc]"'`), `color` (hex / `rgb(...)` / 22 named whitelist), `note`, `tofix` (drives apply pipeline). **Path** must be `data-path` format from watch HTML — see subskills for full pipeline.

---

## L2: DOM Operations

### set — modify properties

```bash
officecli set <file> <path> --prop key=value [--prop ...]
```

**Any XML attribute is settable** via element path (found via `get --depth N`) — even attributes not currently present. Without `find=`, `set` applies format to the entire element.

**Value formats:**

| Type | Format | Examples |
|------|--------|---------|
| Colors | Hex (with/without `#`), named, RGB, theme | `FF0000`, `#FF0000`, `red`, `rgb(255,0,0)`, `accent1`..`accent6` |
| Spacing | Unit-qualified | `12pt`, `0.5cm`, `1.5x`, `150%` |
| Dimensions | EMU or suffixed | `914400`, `2.54cm`, `1in`, `72pt`, `96px` |

**Dotted-attr aliases** — `font.<attr>` forms accepted on shape/run/paragraph/table/row/cell/section/styles, e.g. `--prop font.color=red --prop font.bold=true --prop font.size=14pt`. Run `officecli help <fmt> <element>` for the full list.

### find — format or replace matched text

Use top-level `--find` / `--replace` on `set` (and `--find` on `query`). Legacy `--prop find=X` still works but emits a hint.

```bash
# Format matched text (auto-splits runs)
officecli set doc.docx '/body/p[1]' --find weather --prop bold=true --prop color=red

# Regex matching (regex= still a prop flag)
officecli set doc.docx '/body/p[1]' --find '\d+%' --prop regex=true --prop color=red

# Replace text (use `/` for whole-document scope)
officecli set doc.docx / --find draft --replace final

# docx: tracked Find&Replace
officecli set doc.docx / --find draft --replace final --prop revision.author=Alice

# PPT — same syntax, different paths
officecli set slides.pptx / --find draft --replace final
```

**Path controls search scope:** `/` = whole document, `/body/p[1]` or `/slide[N]/shape[M]` = specific element, `/header[1]` / `/footer[1]` = headers/footers.

**Notes:**
- Case-sensitive by default. Case-insensitive: `--prop 'find=(?i)error' --prop regex=true`
- Matches work across run boundaries
- No match = silent success. `--json` includes `"matched": N`
- **Excel:** only `find` + `replace` supported (no find + format props)

### add — add elements or clone

```bash
officecli add <file> <parent> --type <type> [--prop ...]
officecli add <file> <parent> --type <type> --after <path> [--prop ...]   # insert after anchor
officecli add <file> <parent> --type <type> --before <path> [--prop ...]  # insert before anchor
officecli add <file> <parent> --type <type> --index N [--prop ...]        # 0-based position (legacy)
officecli add <file> <parent> --from <path>                               # clone existing element
```

`--after`, `--before`, `--index` are mutually exclusive. No position flag = append to end.

### move, swap, remove

```bash
officecli move <file> <path> [--to <parent>] [--index N] [--after <path>] [--before <path>]
officecli swap <file> <path1> <path2>
officecli remove <file> '/body/p[4]'
```

When using `--after` or `--before`, `--to` can be omitted — the target container is inferred from the anchor.

### batch — multiple operations in one save cycle

**Atomic by default (v1.0.137+):** every item still runs and is reported (so `N succeeded, M failed` stays meaningful and every failure surfaces), but if *any* item fails the whole batch rolls back — the file on disk is left byte-identical to before the batch ran (confirmed live in both standalone and resident mode). Use `--best-effort` to restore the old apply-what-succeeds behavior (useful for lossy `dump→batch` replays where losing the whole thing over one unsupported item is worse than a partial result). `--stop-on-error` only changes how early the run stops (remaining items are `skipped`), not whether what ran gets kept — combine it with `--best-effort` if you want "stop at first failure but keep what already succeeded." `--force` is unrelated — it's only the docx-protection bypass. Failed items carry a machine-readable `code` field (same list as `error.code`); a rolled-back batch's JSON summary carries `"atomicRolledBack": true`.

`officecli dump <file> [<path>]` emits a replayable batch JSON for round-trip — `.docx` (full coverage), `.pptx` (text/tables/pictures/charts/notes/theme + OLE/3D/video/audio/SmartArt/morph/p15 transitions via raw-set passthrough), and `.xlsx` (cells/formulas/styles + tables, conditional formatting, validations, comments, charts, sparklines, pictures, shapes, pivot tables; slicers/chartEx/OLE via verbatim carrier). Path defaults to `/` (whole document); pass a subtree path (docx: `/body`, `/body/p[N]`, `/body/tbl[N]`, `/theme`, `/settings`, `/numbering`, `/styles`; xlsx: `/SheetName`, `/sheet[N]`) to scope the dump. `officecli refresh <file.docx>` recalculates TOC page numbers / PAGE / cross-references after replay (Word backend on Windows; headless-HTML fallback elsewhere). `officecli plugins list` extends support to `.doc`, `.hwpx`, `.pdf` export.

```bash
echo '[
  {"command":"set","path":"/Sheet1/A1","props":{"value":"Name","bold":"true"}},
  {"command":"set","path":"/Sheet1/B1","props":{"value":"Score","bold":"true"}}
]' | officecli batch data.xlsx --json

officecli batch data.xlsx --commands '[{"op":"set","path":"/Sheet1/A1","props":{"value":"Done"}}]' --json
officecli batch data.xlsx --input updates.json --best-effort --json   # keep whatever succeeds even if some items fail
```

Supports: `add`, `set`, `get`, `query`, `remove`, `move`, `swap`, `view`, `raw`, `raw-set`, `validate`. Fields: `command` (or `op`), `path`, `parent`, `type`, `from`, `to`, `index`, `after`, `before`, `props`, `selector`, `mode`, `depth`, `part`, `xpath`, `action`, `xml`.

---

## L3: Raw XML

Use when L2 cannot express what you need. No xmlns declarations needed — prefixes auto-registered.

```bash
officecli raw <file> <part>                          # view raw XML
officecli raw-set <file> <part> --xpath "..." --action replace --xml '<w:p>...</w:p>'
officecli add-part <file> <parent>                   # create new document part (returns rId)
```

`raw-set` actions: `append`, `prepend`, `insertbefore`, `insertafter`, `replace`, `remove`, `setattr`. Run `officecli help <format> raw` for available parts.

---

## Common Pitfalls

| Pitfall | Correct Approach |
|---------|-----------------|
| `--name "foo"` | Use `--prop name="foo"` — all attributes go through `--prop` |
| Unquoted `[N]` paths in zsh/bash | Always quote: `'/slide[1]'` or `"/slide[1]"` (shell glob-expands brackets) |
| PPT `shape[1]` for content | `shape[1]` is typically the title placeholder. Use `shape[2]+` for content shapes |
| `/shape[myname]` | Name indexing not supported. Use numeric index or `@name=` (PPT only) |
| Guessing property names | Run `officecli help <format> <element>` to see exact names |
| Modifying an open file | Close the file in PowerPoint/WPS first |
| `\n` in shell strings | Use `\\n` for newlines in `--prop text="..."` |
| `$` in shell text | `--prop text="$15M"` strips `$15`. Use single quotes: `--prop text='$15M'`, or heredoc batch |

---

## Specialized Skills

`officecli load_skill <name>` — output is a SKILL.md, follow its rules.

**Loading rule**:
- Pick the most specific match in "When to use"; if none fits, load the format default (`word` / `pptx` / `excel`).
- Scenes already contain the format default's rules — load **one** skill per artifact, never stack.
- Loaded rules persist across turns; don't re-load each reply.
- Two distinct artifacts → two separate loads.

### Word (.docx)

| Name | When to use |
|------|-------------|
| `word` | Reports, letters, memos, proposals, generic documents |
| `academic-paper` | Journal / conference / thesis: APA / Chicago / IEEE / MLA citations, equations, SEQ + PAGEREF cross-refs, multi-column journal layout, bibliography. NOT for business reports or letters (route those to `word`) |

### PowerPoint (.pptx)

| Name | When to use |
|------|-------------|
| `pptx` | Generic decks: board reviews, sales decks, all-hands, product launches |
| `pitch-deck` | **Fundraising only** — seed / Series A-C / SAFE / convertible / strategic raise. NOT for sales / product / board decks (route those to `pptx`) |
| `morph-ppt` | Cinematic Morph-animated presentations. NOT for static decks (route those to `pptx`) |
| `morph-ppt-3d` | 3D Morph: GLB models, camera moves, depth. NOT for 2D-only Morph (route those to `morph-ppt`) |

### Excel (.xlsx)

| Name | When to use |
|------|-------------|
| `excel` | Generic workbooks, formulas, pivots, trackers |
| `financial-model` | Financial models, scenarios, projections. NOT for general data analysis (route those to `excel`) |
| `data-dashboard` | CSV/tabular data → KPI / analytics / executive dashboards with charts and sparklines. NOT for raw data tracking (route those to `excel`) |

Example: a fundraising deck task → `officecli load_skill pitch-deck` → use the printed rules.

---

## Notes

- Paths are **1-based** (XPath convention): `'/body/p[3]'` = third paragraph
- `--index` is **0-based** (array convention): `--index 0` = first position
- **Excel exception**: for `add --type row` and `add --type col`, `--index N` is **1-based** (matches OOXML RowIndex / column letter index). `--index 5` inserts at row 5 / column 5.
- After modifications, verify with `validate` and/or `view issues`
- **When unsure**, run `officecli help <format> <element>` instead of guessing
