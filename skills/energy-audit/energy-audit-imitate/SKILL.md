---
name: energy-audit-imitate
description: Imitate same-type energy-audit reports into Word.
version: 0.2.0
author: matianyuan, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [energy-audit, report, imitate, word]
    category: productivity
    related_skills: [docx]
---

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
- `matplotlib` in the Hermes environment (chart rendering for `[[图:...]]` markers;
  included in the `energy` extra: `uv sync --extra energy`).
- **格式规范**：`references/report-format-spec.md`（19 份省直报告统计标准）是组装
  Word 时必须遵守的格式基准（字体/缩进/表格/目录/水印），先读它再写正文。
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

**Chapter body syntax** (parsed by `assemble_report.py`):

- Heading lines `1.1 标题` / `1.1.1 标题` become H2 / H3 (章标题 `第X章` is
  added automatically).
- Markdown tables: a title line `表X.Y 标题` followed by `| a | b |` rows
  (first row = header, `|---|` separator ignored) renders as a formatted
  Word table (12pt centered, 1.01cm row height).
- Chart markers `[[图:类型|图注]]` render a matplotlib chart from
  `chart_data` and embed it with the caption. Supported types: `flow`
  (energy flow diagram), `trend` (yearly tce bars), `pie` (latest-year
  energy mix), `monthly_electricity_kwh` / `monthly_water_m3` /
  `monthly_natural_gas_m3` (12-month comparison bars). Charts silently
  skip when `chart_data` is missing or matplotlib is absent.
- Assembled output is auto-enriched: Word TOC field with
  `updateFields on open` (目录打开自动生成), DrawingML unit-name watermark
  (injected after save by `scripts/add_watermark.py` — 被审计单位全称，
  禁止 VML textpath), and a footer `第 X 页 共 Y 页` page-number field.
  具体格式细则以 `references/report-format-spec.md` 为准。

### 5. Assemble Word

Write `spec.json`:

```json
{
  "project_name": "<单位>",
  "audit_type": "公共机构",
  "cover": {"title": "<单位>能源审计报告", "audit_organization": "同方德诚科技有限公司"},
  "audit_info_tables": {
    "institution": {"name": "<审计机构名称,ts_register_dept>", "address": "<审计机构详细地址,ts_register_dept/用户提供>",
                    "contact": "<审计机构负责人,用户提供>", "phone": "<审计机构联系方式,用户提供>"},
    "team_members": [{"role": "审计负责人", "name": "…", "education": "…", "certification": "…", "major": "…"}],
    "cooperation": [{"role": "组长", "dept": "…", "name": "…", "gender": "…", "position": "…"}]
  },
  "chart_data": {
    "unit_name": "<单位>",
    "building_area": 20549.74,
    "people_count": 3405,
    "energy_types": ["electricity_kwh", "water_m3", "natural_gas_m3"],
    "years": [
      {"year": 2022, "electricity_kwh": 5090273, "water_m3": 163107.7, "natural_gas_m3": 57207,
       "monthly_electricity_kwh": [444397, 336312, 398512, 406173, 239072, 579033, 653165, 612890, 393904, 251604, 333349, 441862],
       "monthly_water_m3": [14036, 12205.7, 12342, 14396, 11786, 14974, 17622, 16724, 15123, 10678, 11628, 11593],
       "monthly_natural_gas_m3": [5110, 4612, 5107, 4760, 5140, 4480, 4590, 4260, 5049, 4959, 3450, 5690]},
      {"year": 2023, "electricity_kwh": 5225773, "water_m3": 150110.0, "natural_gas_m3": 68483, "monthly_*": "..."},
      {"year": 2024, "electricity_kwh": 4833915, "water_m3": 154167.0, "natural_gas_m3": 79374, "monthly_*": "..."}
    ],
    "equipment": [{"device_name": "冷水机组", "device_num": 2, "power": 298, "category": "空调"}]
  },
  "imitated_chapters": {
    "第1章": "...",
    "第2章": "...",
    "第3章": "...",
    "第4章": "...",
    "第5章": "1.1 ...\n[[图:flow|图5.1 能源资源流向图]]\n...",
    "第6章": "...",
    "第7章": "...",
    "第8章": "..."
  }
}
```

`chart_data.years` entries feed `trend` / `pie` / `monthly_*` charts (pull
them from `energy_audit_get_energy`; monthly arrays are the 12 monthly
values, order Jan–Dec). `equipment` is optional and only used by `flow`.

`terminal` the assemble script. Done when stdout reports `ok` and
`file_path` exists.

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
- Charts need `chart_data`; without it `[[图:...]]` markers render nothing
  (no error). Always populate `chart_data` when the project has energy data.
- `flow` writes a timestamped PNG (`energy_flow_<ts>.png`) so a user who has
  the previous chart open in a viewer doesn't lock the file and drop the image.
- TOC entries appear only after Word/WPS updates fields on open (set
  automatically via `updateFields`); if the user reports an empty 目录, tell
  them Ctrl+A → F9 once.

## Verification

- [ ] Project data came from `energy_audit_get_*` tools (or a stated miss).
- [ ] All eight chapters follow the chosen type's outline.
- [ ] No other unit's identifiers appear in the prose.
- [ ] Assemble script returned `file_path`; the `.docx` is on disk.
- [ ] `chart_data` populated and every `[[图:...]]` marker has a matching
  embedded image (check `word/media/` in the .docx zip).
- [ ] Watermark (DrawingML unit-name, injected by `scripts/add_watermark.py`)
  and page numbers (footer PAGE/NUMPAGES fields) present in the .docx.
