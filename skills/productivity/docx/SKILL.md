---
name: docx
description: Create, read, edit, template, and review Word .docx files.
version: 1.1.0
author: Nous Research
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [word, docx, documents, office, templates, revisions, comments]
    category: productivity
    related_skills: [pdf, xlsx, powerpoint]
---

# Docx Skill

Create, read, edit, and template Microsoft Word `.docx` files with
python-docx via small CLIs. It handles text, styles, lists, tables,
images, headers/footers, `{{token}}` templating, tracked changes
(list/accept/reject), comments (list/add/delete), TOC and page-number
fields, and package health checks. It does not render documents itself
(PDF needs LibreOffice — see Converting to PDF) or edit legacy `.doc`.

## When to Use

- The user asks to generate a Word document (report, letter, contract).
- You need the text, outline, styles, or embedded images of a `.docx`.
- You must change an existing `.docx`: replace text, edit table cells,
  insert/delete paragraphs, apply styles, merge fragmented runs.
- You have a `.docx` template with `{{placeholders}}` to fill from data.
- The document has tracked changes to review, accept, or reject.
- You need to read reviewers' comments, or add/delete comments.
- A `.docx` won't open or behaves oddly and you need corruption triage.
- The document needs a table of contents or "Page X of Y" footers.
- Not for: `.doc` (legacy), `.odt`, or WYSIWYG layout work.

## Prerequisites

- Python 3.10+ with `python-docx` installed:
  `pip install python-docx` (import name is `docx`; lxml comes with it).
- Comments `add` uses the native API on python-docx >= 1.2 and an XML
  fallback on older versions — both are automatic.
- For image blocks: the image files must exist locally (PNG/JPEG).

## How to Run

All helpers live in `scripts/` next to this file. Run them with the
`terminal` tool; each supports `--help` and prints JSON to stdout.

```bash
python scripts/docx_create.py spec.json out.docx
python scripts/docx_read.py out.docx --text
python scripts/docx_edit.py replace out.docx --find old --replace new
python scripts/docx_template.py tpl.docx values.json filled.docx
python scripts/docx_revisions.py list out.docx
python scripts/docx_comments.py list out.docx
python scripts/docx_validate.py out.docx
```

## Quick Reference

| Task | Command |
| --- | --- |
| Create from JSON spec | `docx_create.py spec.json out.docx` |
| Full text (body+tables+headers/footers) | `docx_read.py f.docx --text` |
| Heading outline + table shapes | `docx_read.py f.docx --structure` |
| Styles actually used | `docx_read.py f.docx --styles` |
| Extract embedded images | `docx_read.py f.docx --images outdir/` |
| Detect tracked changes/comments | `docx_read.py f.docx --revisions` |
| Find/replace (formatting kept) | `docx_edit.py replace f.docx --find A --replace B -o out.docx` |
| Set a table cell | `docx_edit.py set-cell f.docx --table 0 --row 1 --col 2 --text X` |
| Insert paragraph before index N | `docx_edit.py insert f.docx --index N --text X --style Normal` |
| Delete paragraph N | `docx_edit.py delete f.docx --index N` |
| Apply style to paragraph N | `docx_edit.py style f.docx --index N --style "Heading 1"` |
| Merge equal-format adjacent runs | `docx_edit.py normalize f.docx -o out.docx` |
| Insert TOC field before para N | `docx_edit.py toc f.docx --index N -o out.docx` |
| "Page X of Y" footer fields | `docx_edit.py page-numbers f.docx` |
| Fill `{{tokens}}` | `docx_template.py tpl.docx values.json out.docx --strict` |
| List revisions (id/author/date/text) | `docx_revisions.py list f.docx` |
| Accept / reject all revisions | `docx_revisions.py accept-all f.docx -o out.docx` (or `reject-all`) |
| Accept / reject one revision | `docx_revisions.py accept f.docx --id 3 -o out.docx` |
| List comments (+anchored text) | `docx_comments.py list f.docx` |
| Add comment anchored to text | `docx_comments.py add f.docx --target "phrase" --text "note" --author You` |
| Delete comment by id | `docx_comments.py delete f.docx --id 0` |
| Health-check the package | `docx_validate.py f.docx` (exit 1 on errors) |

## Procedure

1. **Create.** Write a JSON spec with `write_file`, then run
   `scripts/docx_create.py`. The spec supports: `page` (size + margins in
   mm), `header`/`footer` strings, `footer_page_numbers` (adds a
   "Page X of Y" field footer), `styles` (custom paragraph styles with
   font, size, bold/italic, hex `color`), and `blocks` — `heading`
   (level 1-9), `paragraph` (either `text` or a `runs` list where each run
   may set `bold`/`italic`/`underline`), `bullet_list`, `numbered_list`,
   `table` (`header` row rendered bold, `rows`, optional built-in table
   `style` such as `Table Grid`), `image` (`path`, optional `width_mm`),
   `toc` (Table of Contents field), and `page_break`. The full spec
   format is documented at the top of `scripts/docx_create.py`.
2. **Read.** Use `scripts/docx_read.py` with exactly one mode flag.
   `--text` returns body paragraphs, all table cell text, and
   header/footer text as JSON. `--structure` returns the heading outline
   plus paragraph/table/section counts. `--images DIR` copies every file
   under `word/media/` out of the package.
3. **Edit.** Use `scripts/docx_edit.py`. `replace` walks body, tables
   (nested included), headers and footers, and preserves run formatting;
   add `--body-only` to skip headers/footers. Pass `-o out.docx` to keep
   the original; omit it to edit in place. Paragraph indices for
   `insert`/`delete`/`style`/`toc` refer to `--structure`/`--text` body
   order. Run `normalize` first on documents that came out of heavy Word
   editing — it merges adjacent runs with identical formatting so later
   find-replace matches reliably.
4. **Review revisions.** `docx_revisions.py list` reports every `w:ins`
   and `w:del` (id, author, date, affected text) anywhere in body,
   tables, headers, or footers. `accept-all` / `reject-all` resolve them
   in bulk; `accept`/`reject --id N` handles a single revision. Accept
   keeps insertions and drops deleted text; reject does the reverse.
5. **Comments.** `docx_comments.py list` returns each comment's id,
   author, date, body text, and the document text it is anchored to.
   `add --target "some phrase"` anchors a new comment to the first
   occurrence of that phrase (runs are split as needed; formatting is
   preserved). `delete --id N` removes the comment and its markers
   without touching document text.
6. **Template.** Put `{{name}}`-style tokens in the document. Run
   `scripts/docx_template.py` with a JSON object of values. Use
   `--strict` to fail when tokens remain unfilled; the JSON output lists
   `filled` counts and `unfilled_tokens` either way.
7. **Verify** (always): re-read the output with `--text` or
   `--structure`, and run `docx_validate.py` on anything you produced
   via revision/comment surgery.

## Converting to PDF

No script needed. When LibreOffice is installed, convert headlessly:

```bash
soffice --headless --convert-to pdf --outdir outdir/ file.docx
```

Check availability first (`command -v soffice || command -v
libreoffice`). If neither exists, tell the user PDF conversion is
unavailable in this environment rather than improvising — python-docx
cannot render PDFs, and layout fidelity requires a real renderer.

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

- **Tokens split across runs.** Word often fragments text into several
  runs. The replace helpers collapse matched runs (replacement inherits
  the first run's formatting); running `docx_edit.py normalize` first
  reduces fragmentation for all later edits.
- **Revision coverage.** `docx_revisions.py` resolves run-level
  insertions and deletions (the overwhelming majority). Paragraph-mark
  and table-row revisions, format-change records, and moves are detected
  by `--revisions` but not auto-resolved — see
  `references/revisions-and-comments.md` and hand those to Word.
- **Comment threading.** Replies and "resolved" status live in
  `commentsExtended.xml`, which this skill ignores; comments it adds are
  plain top-level comments.
- **Field results are computed by Word.** `toc`, `page-numbers`, and the
  `toc`/`footer_page_numbers` spec options write *field codes*.
  Word/LibreOffice populates the actual entries and numbers when the
  file is opened (Word may prompt to update fields); python-docx never
  computes them, so placeholder text shows until then.
- **Validation is a health check, not schema validation.**
  `docx_validate.py` verifies the zip, required parts, relationship
  targets, image magic bytes, and referenced styles. It is NOT XSD
  validation — a file can pass and still contain XML Word dislikes.
- **Style names must exist.** Applying a style that isn't defined in the
  document raises `KeyError`. Built-ins like `Heading 1`, `List Bullet`,
  `List Number`, `Table Grid` exist in the default template; custom
  styles must be declared in the create spec first.
- **Numbered lists restart.** `List Number` relies on Word's default
  numbering; separate lists in one document may continue numbering
  instead of restarting. Warn users needing precise multi-list numbering.
- **Cell writes replace formatting.** `set-cell` uses `cell.text = ...`,
  which resets runs in that cell to plain formatting.
- **Encoding.** All JSON specs/values files are read as UTF-8 explicitly;
  never rely on locale defaults when writing your own glue code.
- **Don't unzip-and-sed the XML.** Edit through the scripts (or
  python-docx); raw text substitution in `document.xml` corrupts files
  easily. Use `patch`/`write_file` only for the JSON inputs, never on the
  `.docx` itself.
- Don't round-trip OOXML through `xml.etree.ElementTree` — it rewrites namespace prefixes and corrupts the file. Use `defusedxml.minidom`.
- Zip from INSIDE the unpacked directory (`cd unpacked && zip -Xr ../out.docx .`) and `rm` the target first, or deleted parts survive in the archive.

---

- After create/edit/template, run `docx_read.py out.docx --text` and
  check the expected strings appear (and old strings are gone).
- After accept/reject, `docx_revisions.py list` should return `[]` (or
  only the ids you intentionally left); after comment surgery,
  `docx_comments.py list` should reflect the change and `--text` output
  must be unchanged.
- `docx_validate.py out.docx` exits 0 with `"ok": true` on a healthy
  package — run it after any revision/comment/field manipulation.
- For templates run with `--strict`, or check `unfilled_tokens == []`.
- Structure checks: `--structure` should show the expected heading
  outline and table shapes; `--styles` confirms custom styles applied.
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
