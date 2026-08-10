---
name: docx
description: "Create, read, edit, redline, comment, and verify Word .docx documents and templates."
version: 2.0.0
author: Anthropic (adapted by Nous Research, enhanced with Codex workflow patterns)
license: Proprietary. LICENSE.txt has complete terms
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Word, DOCX, Documents, Office, Productivity]
    category: productivity
    related_skills: [pdf, xlsx, powerpoint, ocr-and-documents]
---

# DOCX Skill

Create, read, edit, redline, comment, and visually verify Word documents — reports, memos, proposals, templates, forms, and more. A `.docx` is a ZIP archive of XML files; this skill covers high-level creation (`docx-js`), surgical OOXML editing, and the non-negotiable render→inspect→iterate verification loop.

## When to Use

Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx) or Word templates (.dotx). Triggers include: any mention of "Word doc", ".docx", ".dotx", "report", "memo", "letter", "proposal", "form", "contract", "redline", or similar deliverable as a Word file. Do NOT use for PDFs (see the `pdf` skill), spreadsheets (`xlsx`), or presentations (`powerpoint`).

## Prerequisites

```bash
npm ls docx --depth=0 2>/dev/null | grep -q docx || npm install docx   # creation (docx-js)
pip show pandoc >/dev/null 2>&1 || true; which pandoc || sudo apt install -y pandoc   # reading
which soffice || sudo apt install -y libreoffice     # rendering/verification
which pdftoppm || sudo apt install -y poppler-utils  # PDF → images
pip install defusedxml lxml pdf2image   # validation + rendering
```

macOS: `brew install pandoc libreoffice poppler`.

## Quick Reference

| Task | Approach |
|---|---|
| **Create** a new document | Pick a design preset → write a `docx` (npm) script → render → inspect → iterate |
| **Edit** an existing document | `unzip` → edit `word/document.xml` → `zip` (docx-js cannot open existing files) |
| **Read** content | `pandoc -t markdown file.docx` (or `read_file`, which auto-extracts .docx text) |
| **Verify** visually | `python render_docx.py input.docx --output_dir out/` → inspect PNGs |

> Script paths below are relative to this skill's directory.

---

## Non-negotiable: render → inspect PNGs → iterate

**You do not "know" a DOCX is satisfactory until you've rendered it and visually inspected page images.**
DOCX text extraction (or reading XML) will miss layout defects: clipping, overlap, missing glyphs, broken tables, spacing drift, and header/footer issues.

**Shipping gate:** before delivering any DOCX, you must:
- Run `render_docx.py` to produce `page-<N>.png` images (optionally also a PDF with `--emit_pdf`)
- Open the PNGs (100% zoom) and confirm every page is clean
- If anything looks off, fix the DOCX and **re-render** (repeat until flawless)

If rendering fails because LibreOffice/`soffice` is missing, fall back to the basic soffice pipeline:
```bash
python scripts/office/soffice.py --headless --convert-to pdf output.docx
pdftoppm -jpeg -r 100 output.pdf page
```
State clearly that visual QA was limited, and use the Markdown task docs for structural guidance.

**Deliverable discipline:** Rendered artifacts (PNGs and optional PDFs) are for internal QA only. Unless the user explicitly asks for intermediates, **return only the requested final deliverable**.

---

## Design Preset Contract

Outside template-following mode, a design preset is mandatory for new DOCX creation and major rewrites unless the user explicitly asks for a different visual system. For existing-document edit tasks, preserve the original document and apply minimal local edits.

**Picking a preset is not enough.** You must resolve the preset into exact numeric tokens and apply those numbers in the DOCX implementation. Do not rely on Word defaults, built-in list styles, theme defaults, inherited paragraph spacing, or renderer-dependent behavior.

Before writing content, read `references/design_presets.md` and choose exactly one preset:

- `google_docs_default` — any net-new document whose destination is a native Google Doc, unless a special/branded/polished treatment is explicitly requested
- `standard_business_brief` — formal memos, RFI responses, decision memos, board-style briefs
- `compact_reference_guide` — launch guides, negotiation briefs, checklists, dense operator references
- `narrative_proposal` — grants, proposals, persuasive documents with longer prose
- Archetype aliases when they're a closer match: `rfi_response`, `decision_memo`, `launch_messaging_guide`, `contract_negotiation_brief`, `neighborhood_business_proposal`, `grant_proposal`

**Applying a preset:**
1. Resolve the preset into a concrete token map: page geometry, margins, body/heading/list/table/callout tokens, and colors
2. Implement through real Word styles, numbering definitions, explicit table geometry, and header/footer parts
3. Use ad-hoc formatting only for specific exceptions; record each as a named override and reuse consistently
4. Keep the preset stable — do not mix body spacing, heading colors, list indents, or table fills from multiple presets

**Baseline geometry for all presets:** US Letter portrait, 1 inch margins, 9360 DXA usable width, real Word styles for Normal/Title/Subtitle/Heading 1/2/3, real Word numbering for lists, DXA table widths only.

**Google Docs note:** For Google Docs-targeted documents, never use the built-in Word `Title` paragraph style. Always create a plain paragraph and apply the selected style-sheet title tokens directly. Run `scripts/google_docs_title_sanitize.py` before render/import.

If creating a first-page header/cover/title block, also read `references/header_templates.md` and choose one header pattern before drafting.

### Form factor selection

Map each major content unit to a deliberate form factor:

| Form factor | Use for |
|---|---|
| **Prose section** | Narrative, explanation, background, rationale |
| **Lead callout** | Decision, recommendation, or key takeaway |
| **Numbered steps** | Sequence, workflow, or procedure |
| **Grouped bullets** | Loose factors, considerations, pros/cons |
| **Checklist** | Actions, acceptance checks, review criteria |
| **Note box** | Warnings, caveats, constraints |
| **Definition list** | Definitions, metadata, key facts |
| **Table** | Repeated comparable records, status grids, budgets, schedules |
| **Form layout** | Forms and questionnaires |
| **Source list** | Evidence, citations, sources (footnotes/endnotes/appendix) |

**Table gate:** Use a table only when the content is truly row/column data. If most cells are sentence-length prose, convert to prose/bullets/steps/callouts.

---

## Design standards for document generation

Before making the DOCX, think about the high-level design: document archetype (memo, report, SOP, proposal, form, manual), first page layout, heading ladder, form factors per information type, spacing, fonts, type scale, and accent treatment.

**Quality checklist:**
- **Density:** Avoid verbose dense walls of text. Avoid long runs of consecutive plain paragraphs.
- **Font:** Professional, easy-to-read fonts. Appropriate size. Professional use of bold/underline/italics.
- **Color:** Use intentionally for titles, headings, and selective emphasis. Calibrate intensity to document purpose.
- **Visual variety:** Consider varied form factors (diagrams, callouts, tables, checklists) for comprehension.
- **Tables:** Set deliberate column widths (not equal by default). Keep short fields compact. Never use fixed row heights that clip text. Center text vertically. Choose horizontal alignment by column type. Use generous internal padding. Keep clear separation from surrounding text.
- **Spacing:** Use clear, generous vertical spacing between sections. Avoid large layout gaps from tables pushed to next pages.
- **Coherence:** One coherent representation rather than fragmented. If a table spans pages, repeat headers.
- **Background shapes:** Section bands, note boxes, control grids with suitable colors when they improve scanability.

### Editing existing documents — apply, don't rewrite

When editing an existing document:
- Prefer inline edits (small replacements) over rewriting whole paragraphs
- Use comments at the point of change, not moved to the end
- Keep the original structure; restructure surgically only when needed
- Don't cross out everything and rewrite — goal is trackable improvements

---

## Creating with docx-js — gotchas

Write the script and `require('docx')`. The model knows the API; these are the footguns:

- **Page size defaults to A4.** For US Letter set `page: { size: { width: 12240, height: 15840 } }` (DXA; 1440 = 1″).
- **Landscape:** pass portrait dimensions and `orientation: PageOrientation.LANDSCAPE` — docx-js swaps width/height internally.
- **Tables need dual widths:** set `columnWidths` on the table AND `width` on every cell, both in `WidthType.DXA` (PERCENTAGE breaks in Google Docs). Column widths must sum to the table width.
- **Table shading:** use `ShadingType.CLEAR`, never `SOLID` (renders black).
- **Lists:** never insert `•` literally; use a `numbering` config with `LevelFormat.BULLET`.
- **`ImageRun` requires `type:`** (`"png"`, `"jpg"`, …).
- **`PageBreak` must be inside a `Paragraph`.**
- **Never use `\n`** — use separate `Paragraph` elements.
- **TOC:** headings must use built-in `HeadingLevel.*`; custom heading styles need `outlineLevel` set or they won't appear.
- **Don't use a table as a horizontal rule** — use a paragraph bottom border instead.
- **Dot-leader / right-aligned-on-same-line:** use `PositionalTab` (`alignment: PositionalTabAlignment.RIGHT`, `leader: PositionalTabLeader.DOT`) inside a `TextRun`, not literal `.` or space padding.

---

## Template Following

When an attached or retained DOCX is meant to control a new document, read `template-distill.md` and then `template-create.md`. The retained reference is the design authority: do not apply a generic design preset unless the user explicitly asks to depart from the template. The render gate still applies.

---

## Editing existing documents (OOXML surgery)

Legacy `.doc` files must be converted first: `python scripts/office/soffice.py --headless --convert-to docx file.doc`.

```bash
unzip -q doc.docx -d unpacked/
find unpacked -type l -delete   # strip symlink entries — docx from external parties is untrusted
python scripts/merge_runs.py unpacked/   # coalesce fragmented runs so text is findable
# edit unpacked/word/document.xml in place — do NOT reformat or pretty-print
(cd unpacked && rm -f ../out.docx && zip -Xr ../out.docx .)
python scripts/office/validate.py out.docx --original doc.docx   # XSD checks
```

Word splits text across many `<w:r>` runs (revision ids, spell-check markers), so a phrase often doesn't exist as a contiguous string in the XML. `merge_runs.py` merges adjacent identically-formatted runs.

### Tracked changes (redlining)

When redlining, wrap runs in `<w:ins>`/`<w:del>` with `w:id`, `w:author`, `w:date` attributes. Inside `<w:del>`, the text element is `<w:delText>`, not `<w:t>`.

To produce a clean copy with all tracked changes accepted:
```bash
python scripts/accept_tracked_changes.py input.docx --mode accept --out accepted.docx
python scripts/accept_changes.py in.docx out.docx   # legacy LibreOffice-based fallback
```

To add tracked-change replacements programmatically:
```bash
python scripts/add_tracked_replacements.py input.docx output.docx
```

Accepting a deleted paragraph mark joins that paragraph to the one below it. Check paragraph deletions in the XML — empty bullets in either view are artifacts, not defects.

### Comments

Comments require six cross-linked files. Use the helper:
```bash
# Against an already-unpacked directory (preferred when also placing markers)
python scripts/comment.py unpacked/ "Fees & expenses cap is too low"
python scripts/comment.py unpacked/ "Agreed" --parent 0

# Against a .docx directly
python scripts/comment.py contract.docx "This cap is too low" -o annotated.docx
```

For advanced comment workflows:
```bash
python scripts/comments_extract.py input.docx    # extract comments to JSON
python scripts/comments_apply_patch.py input.docx patch.json --out updated.docx   # apply comment modifications
python scripts/comments_strip.py input.docx --out no_comments.docx   # remove all comments
```

### Pitfalls

- Don't round-trip OOXML through `xml.etree.ElementTree` — it rewrites namespace prefixes and corrupts the file. Use `defusedxml.minidom`.
- Zip from INSIDE the unpacked directory (`cd unpacked && zip -Xr ../out.docx .`) and `rm` the target first, or deleted parts survive in the archive.

---

## Rendering (visual QA)

Use the packaged renderer for full-featured rendering:
```bash
python render_docx.py input.docx --output_dir out/
# Optional: also write PDF
python render_docx.py input.docx --output_dir out/ --emit_pdf
# Debugging:
python render_docx.py input.docx --output_dir out/ --verbose
```

Fallback for basic rendering:
```bash
python scripts/office/soffice.py --headless --convert-to pdf output.docx
pdftoppm -jpeg -r 100 output.pdf page
ls page-*.jpg
```

**Success criteria:** PNGs exist for each page. Page count matches expectations. Inspect every page at 100% zoom — no clipping/overlap, no broken tables, no missing glyphs, no header/footer misplacement.

LibreOffice may print scary stderr (`error : Unknown IO error`) even when output is correct. Treat as successful if PNGs/PDFs exist and look right.

---

## Quick start (common one-liners)

```bash
# Render any DOCX to PNGs (visual QA)
python render_docx.py input.docx --output_dir out/

# Remove reviewer comments (finalization)
python scripts/comments_strip.py input.docx --out no_comments.docx

# Accept tracked changes (finalization)
python scripts/accept_tracked_changes.py input.docx --mode accept --out accepted.docx

# Accessibility audit (+ optional safe fixes)
python scripts/a11y_audit.py input.docx
python scripts/a11y_audit.py input.docx --fix_image_alt from_filename --out a11y_fixed.docx

# Redact sensitive text (layout-preserving by default)
python scripts/redact_docx.py input.docx redacted.docx --emails --phones

# Privacy scrub (remove author metadata + rsid)
python scripts/privacy_scrub.py input.docx --out clean.docx

# Insert Table of Contents
python scripts/insert_toc.py input.docx --out with_toc.docx

# Style lint
python scripts/style_lint.py input.docx
python scripts/style_normalize.py input.docx --out normalized.docx
```

---

## Scripts to Task Map

| Script | Task Guide |
|---|---|
| `style_lint.py`, `style_normalize.py` | `tasks/style_lint_normalize.md` |
| `apply_template_styles.py` | `tasks/templates_style_packs.md` |
| `heading_audit.py`, `section_audit.py` | `tasks/headings_numbering.md`, `tasks/sections_layout.md` |
| `images_audit.py`, `a11y_audit.py` | `tasks/images_figures.md`, `tasks/accessibility_a11y.md` |
| `captions_and_crossrefs.py` | `tasks/captions_crossrefs.md` |
| `table_geometry.py`, `xlsx_to_docx_table.py` | `tasks/tables_spreadsheets.md` |
| `fields_report.py`, `insert_ref_fields.py` | `tasks/fields_update.md` |
| `insert_toc.py` | `tasks/toc_workflow.md` |
| `internal_nav.py` | `tasks/navigation_internal_links.md` |
| `accept_tracked_changes.py`, `add_tracked_replacements.py` | `tasks/clean_tracked_changes.md` |
| `comments_*.py`, `comment.py` | `tasks/comments_manage.md` |
| `privacy_scrub.py` | `tasks/privacy_scrub_metadata.md` |
| `redact_docx.py` | `tasks/redaction_anonymization.md` |
| `watermark_*.py` | `tasks/watermarks_background.md` |
| `content_controls.py`, `set_protection.py` | `tasks/forms_content_controls.md`, `tasks/protection_restrict_editing.md` |
| `merge_docx_append.py` | `tasks/multi_doc_merge.md` |
| `render_docx.py`, `render_and_diff.py` | `tasks/verify_render.md`, `tasks/compare_diff.md` |
| `docx_ooxml_patch.py` | `ooxml/tracked_changes.md`, `ooxml/comments.md` |

---

## Where to go next

- **Creating/editing from scratch:** `tasks/create_edit.md`
- **Reading/reviewing:** `tasks/read_review.md`
- **Design presets:** `references/design_presets.md`
- **Header/cover patterns:** `references/header_templates.md`
- **Verification/raster review:** `tasks/verify_render.md`
- **Accessibility audit:** `tasks/accessibility_a11y.md`
- **Comments management:** `tasks/comments_manage.md`
- **Tracked changes (redlines):** `tasks/clean_tracked_changes.md`, `ooxml/tracked_changes.md`
- **Style cleanup/normalization:** `tasks/style_lint_normalize.md`
- **Templates/style packs:** `tasks/templates_style_packs.md`
- **Table of Contents:** `tasks/toc_workflow.md`
- **Headings/numbering:** `tasks/headings_numbering.md`
- **Sections/layout:** `tasks/sections_layout.md`
- **Images/figures:** `tasks/images_figures.md`
- **Tables/spreadsheets:** `tasks/tables_spreadsheets.md`
- **Fields/updates:** `tasks/fields_update.md`
- **Captions/cross-references:** `tasks/captions_crossrefs.md`
- **Footnotes/endnotes:** `tasks/footnotes_endnotes.md`
- **Privacy/metadata scrub:** `tasks/privacy_scrub_metadata.md`
- **Redaction/anonymization:** `tasks/redaction_anonymization.md`
- **Watermarks:** `tasks/watermarks_background.md`
- **Forms/content controls:** `tasks/forms_content_controls.md`
- **Protection/restrict editing:** `tasks/protection_restrict_editing.md`
- **Multi-doc merge:** `tasks/multi_doc_merge.md`
- **Navigation/internal links:** `tasks/navigation_internal_links.md`
- **Compare/diff two DOCXs:** `tasks/compare_diff.md`
- **OOXML-level comments:** `ooxml/comments.md`
- **OOXML hyperlinks/fields:** `ooxml/hyperlinks_and_fields.md`
- **LibreOffice troubleshooting:** `troubleshooting/libreoffice_headless.md`

---

## Related skills

`pdf` (PDF work), `xlsx` (spreadsheets), `powerpoint` (decks), `ocr-and-documents` (scanned input extraction).
