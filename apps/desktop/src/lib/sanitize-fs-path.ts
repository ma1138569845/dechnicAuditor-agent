/**
 * Peel Markdown / quote wrappers off a filesystem path the model emphasized.
 *
 * `**MEDIA: ~/out/a.docx**` and `[report](~/out/a.docx**)` leak `*` into the
 * path. Those characters are never meaningful on a path we preview (illegal
 * on Windows; URL autolink already drops them). Underscores stay conservative:
 * a trailing `_` is removed only when it follows a file extension (`a.docx_`,
 * italic closer). A file named `/tmp/draft_` is left alone. Wrapping
 * `_path_` / `__path__` is peeled only when the inside already looks like a path.
 */

const WRAP_UNDERSCORE_RE = /^(__?)((?:\/|~\/|[A-Za-z]:[\\/]).+)\1$/
const TRAILING_EXT_UNDERSCORE_RE = /(\.[A-Za-z0-9]{1,8})_$/

export function sanitizeFsPath(value: string): string {
  let path = value.trim()

  if (!path) {
    return path
  }

  const quote = path[0]

  if (path.length >= 2 && quote === path.at(-1) && (quote === '"' || quote === "'" || quote === '`')) {
    path = path.slice(1, -1).trim()
  }

  path = path.replace(/^\*+/, '').replace(/\*+$/, '')

  const wrapped = WRAP_UNDERSCORE_RE.exec(path)

  if (wrapped) {
    path = wrapped[2]
  }

  path = path.replace(TRAILING_EXT_UNDERSCORE_RE, '$1')
  path = path.replace(/[),.;]+$/, '')
  path = path.replace(/^`+/, '').replace(/`+$/, '')

  return path.trim()
}
