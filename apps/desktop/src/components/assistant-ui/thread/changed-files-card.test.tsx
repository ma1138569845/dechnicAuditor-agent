import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router'

import { ChangedFilesCard } from '@/components/assistant-ui/thread/changed-files-card'
import { I18nProvider } from '@/i18n'
import { normalizeOrLocalPreviewTarget } from '@/lib/local-preview'
import { $previewTabs, closeRightRail } from '@/store/preview'

vi.mock('@/lib/local-preview', () => ({
  normalizeOrLocalPreviewTarget: vi.fn()
}))

const PATCH_DIFF = '--- a/src/demo.ts\n+++ b/src/demo.ts\n@@ -1 +1 @@\n-old\n+new\n'

function writePart(path: string, content: string) {
  return {
    args: { content, path },
    result: { bytes_written: new TextEncoder().encode(content).length },
    toolName: 'write_file',
    type: 'tool-call'
  }
}

function renderCard(parts: unknown[]) {
  return render(
    <MemoryRouter>
      <I18nProvider configClient={null} initialLocale="en">
        <ChangedFilesCard parts={parts} />
      </I18nProvider>
    </MemoryRouter>
  )
}

describe('ChangedFilesCard', () => {
  beforeEach(() => {
    closeRightRail()
    window.localStorage.clear()
    vi.mocked(normalizeOrLocalPreviewTarget).mockImplementation(async (path: string) => ({
      kind: 'file' as const,
      label: path.split(/[\\/]/).pop() || path,
      path,
      previewKind: path.endsWith('.html') ? ('html' as const) : ('text' as const),
      source: path,
      url: `file://${path}`
    }))
  })

  afterEach(() => {
    cleanup()
    closeRightRail()
    window.localStorage.clear()
  })

  it('renders nothing when the turn wrote no files', () => {
    const { container } = renderCard([])

    expect(container.querySelector('[data-slot="aui_changed-files"]')).toBeNull()
  })

  it('shows a file tile with size and opens the right-rail preview on click', async () => {
    renderCard([writePart('notes.md', 'hello world')])

    expect(screen.getByText('notes.md')).toBeTruthy()
    expect(screen.getByText('11 B')).toBeTruthy()
    expect(screen.getByText('View all artifacts (1)')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Open notes.md' }))

    await waitFor(() => {
      expect($previewTabs.get()).toHaveLength(1)
    })

    expect($previewTabs.get()[0]?.target).toMatchObject({
      kind: 'file',
      path: 'notes.md',
      previewKind: 'text'
    })
  })

  it('marks html files as live-previewable and opens them as a rendered preview', async () => {
    renderCard([
      {
        args: { path: 'cowriting_sidebar.html' },
        result: { bytes_written: 9728, success: true },
        toolName: 'write_file',
        type: 'tool-call'
      }
    ])

    expect(screen.getByText('cowriting_sidebar.html')).toBeTruthy()
    expect(screen.getByText('9.5 KB')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Open cowriting_sidebar.html' }))

    await waitFor(() => {
      expect($previewTabs.get()[0]?.target.previewKind).toBe('html')
    })
  })

  it('caps the grid at four tiles until view-all expands the rest', () => {
    renderCard([
      writePart('a.py', 'a'),
      writePart('b.py', 'b'),
      writePart('c.py', 'c'),
      writePart('d.py', 'd'),
      writePart('e.py', 'e')
    ])

    expect(screen.getByText('a.py')).toBeTruthy()
    expect(screen.getByText('d.py')).toBeTruthy()
    expect(screen.queryByText('e.py')).toBeNull()

    fireEvent.click(screen.getByText('View all artifacts (5)'))

    expect(screen.getByText('e.py')).toBeTruthy()
  })

  it('still shows a patch with a persisted diff', () => {
    renderCard([
      {
        args: { path: 'src/demo.ts' },
        result: { diff: PATCH_DIFF, success: true },
        toolName: 'patch',
        type: 'tool-call'
      }
    ])

    expect(screen.getByText('demo.ts')).toBeTruthy()
  })
})
