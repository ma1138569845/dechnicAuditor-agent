/**
 * Resolve a path under Vite's `public/` (or built `dist/`) for both
 * `http://` (dev / dashboard) and packaged Electron `file://` loads.
 *
 * Root-absolute URLs like `/assets/foo.png` resolve to the filesystem
 * root under `file://` and silently 404. Always prefix with
 * `import.meta.env.BASE_URL` (Vite `base: './'` → `./`).
 */
export function assetPath(path: string, baseUrl: string = import.meta.env.BASE_URL): string {
  return `${baseUrl}${path.replace(/^\/+/, '')}`
}
