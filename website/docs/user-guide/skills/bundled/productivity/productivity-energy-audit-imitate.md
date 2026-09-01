---
title: "Energy Audit Imitate — Imitate same-type energy-audit reports into Word"
sidebar_label: "Energy Audit Imitate"
description: "Imitate same-type energy-audit reports into Word"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Energy Audit Imitate

Imitate same-type energy-audit reports into Word.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/productivity/energy-audit-imitate` |
| Version | `0.1.0` |
| Author | matianyuan, Hermes Agent |
| License | MIT |
| Platforms | linux, macos, windows |
| Tags | `energy-audit`, `report`, `imitate`, `word` |
| Related skills | [`docx`](/docs/user-guide/skills/bundled/productivity/productivity-docx) |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Hermes loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Energy Audit Report Imitation Skill

Write a full energy-audit Word report by imitating same-type references with
**this project's** numbers. The agent writes every chapter. It does not call
the scripted REST/pipeline path (`energy_audit_imitate_report`).

## When to Use

- The user asks to 仿写 an energy-audit report for a named unit.
- The desktop dialog submits `/energy-audit-imitate` after choosing 智能体任务.
- The user wants chapter prose in the style of similar reports, not a fixed template fill.

Don't use for: 标准模板 generation (desktop 脚本实现 + 标准模板), a single
paragraph (then `energy_audit_imitate_paragraph` is enough), or editing an
existing `.docx` layout (`docx`).

## Prerequisites

- `energy_audit` toolset enabled; PostgreSQL reachable for project data.
- `energy_audit_rag_search` available when Qdrant/wiki has ingested reports.
- `python-docx` in the Hermes environment (needed by `scripts/assemble_report.py`).
- Optional local reference folder: `EA_REFERENCE_DIR` or
  `{HERMES_HOME}/rag/report/{省}/{市}/{区县}/{审计类型}/`.
  On Windows this is `%LOCALAPPDATA%\hermes\rag\report` (not `~/.hermes`).
  Filenames that contain the place also match.

## How to Run

Write chapters to a JSON spec, then assemble Word with `terminal`:

```text
terminal(command="python scripts/assemble_report.py spec.json reports/<单位>能源审计报告.docx")
```

Run from this skill directory. `--help` prints usage. Stdout is JSON
`{"ok": true, "file_path": "..."}`.

## Quick Reference

| Step | Tool |
| --- | --- |
| Find unit | `energy_audit_search_projects` |
| Load project | `energy_audit_get_project` |
| Buildings / equipment / energy | `energy_audit_get_buildings`, `energy_audit_get_equipment`, `energy_audit_get_energy` |
| Same-type references | `energy_audit_rag_search` |
| Chapter outline | `read_file` `references/chapter-outlines.md` |
| Page / TOC / watermark | `read_file` `references/report-format-spec.md` |
| Word assemble | `terminal` `python scripts/assemble_report.py …` |

## Procedure

### 1. Lock the target

Read the slash instruction for 单位/项目名称 and 审计类型 (`公共机构` /
`公共建筑` / `工业企业`). If the type is missing, take it from the project
record after step 2. Done when both name and type are stated.

### 2. Load this project's data

Call `energy_audit_search_projects`, then `energy_audit_get_project` on the
chosen row. Pull buildings, equipment, and energy (and meters when needed).
Treat database values as the only numeric source of truth. Done when the
unit is found or a missing-project error is reported to the user (stop; do
not invent a unit).

### 3. Collect same-region, same-type references

Prefer reports from the same 区县, then 地市, then 省份, then the same
audit type. Read `province` / `city` / `district` from the project, or
infer them from the unit name and address.

Call `energy_audit_rag_search` with those place names **in the query
string** (do not pass them as payload filters). Also pass `audit_type`
and institution/specific type when known. Query per chapter theme
(概况、计量、指标、系统、潜力). Optionally `search_files` under
`{HERMES_HOME}/rag/report/{省}/{市}/{区县}/{类型}/`. Done when at least
one same-region or same-type source is cited, or the gap is stated and
writing continues on data + outline only.

### 4. Imitate all eight chapters

`read_file` `references/chapter-outlines.md` for this audit type. For each
chapter: copy **rhetorical structure** (heading order, table habits, how
findings are hedged) from references; fill **facts and numbers** only from
this project. Never copy another unit's name, area, headcount, or kWh.
Mark missing meters/years as 数据不足 — do not fabricate. Done when 第1章
through 第8章 each have body text with the outline's subsection headings.

### 5. Assemble Word

`read_file` `references/report-format-spec.md`. Write `spec.json` with the
unit full name (watermark text) and all eight chapters:

```json
{
  "project_name": "<单位>",
  "unit_name": "<被审计单位全称>",
  "audit_type": "公共机构",
  "cover": {"title": "<单位>能源审计报告"},
  "imitated_chapters": {
    "第1章": "...",
    "第2章": "...",
    "第3章": "...",
    "第4章": "...",
    "第5章": "...",
    "第6章": "...",
    "第7章": "...",
    "第8章": "..."
  }
}
```

`terminal` the assemble script (it writes the TOC field and DrawingML
watermark). Done when stdout reports `ok`, `file_path` exists, and the spec
had a non-empty `unit_name`.

### 6. Hand the file back

Tell the user the `.docx` path and which references informed the style.
Done when the path is in the reply.

## Pitfalls

- Do **not** call `energy_audit_imitate_report` or `POST /api/energy-audit/generate`.
  That is the 脚本实现 path; this skill exists so the agent writes the prose.
- Do not paste reference numbers, unit names, or honorifics into this report.
- Do not mix 公共机构 / 公共建筑 / 工业企业 outlines.
- `energy_audit_imitate_paragraph` is a last resort for one stuck section, not
  the default for the full report.
- Empty `imitated_chapters` keys fail assemble; fill all eight before running it.
- Do not skip the TOC field or replace the DrawingML watermark with grey
  body text / VML `textpath`. Watermark text is `unit_name`, not the report title.

## Verification

- [ ] Project data came from `energy_audit_get_*` tools (or a stated miss).
- [ ] All eight chapters follow the chosen type's outline.
- [ ] No other unit's identifiers appear in the prose.
- [ ] Assemble script returned `file_path`; the `.docx` is on disk.
- [ ] Word has a 目录 field; watermark is the unit full name (DrawingML).
