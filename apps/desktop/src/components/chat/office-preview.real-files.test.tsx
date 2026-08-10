import { readFileSync } from 'node:fs'
import path from 'node:path'

import { cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'
import { readDesktopFileDataUrl } from '@/lib/desktop-fs'

import { OfficePreview } from './office-preview'

vi.mock('@/lib/desktop-fs', () => ({
  readDesktopFileDataUrl: vi.fn()
}))

const SAMPLES_DIR = path.resolve(__dirname, '../../../.sample-office')

function dataUrlFromFile(fileName: string, mimeType: string): string {
  const bytes = readFileSync(path.join(SAMPLES_DIR, fileName))

  return `data:${mimeType};base64,${bytes.toString('base64')}`
}

function renderOffice(officeKind: 'docx' | 'xlsx' | 'pptx', fileName: string) {
  return render(
    <I18nProvider configClient={null}>
      <OfficePreview filePath={path.join(SAMPLES_DIR, fileName)} officeKind={officeKind} />
    </I18nProvider>
  )
}

describe('OfficePreview real file integration', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders sample.docx through mammoth', async () => {
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(
      dataUrlFromFile('sample.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    )

    const { container } = renderOffice('docx', 'sample.docx')

    await waitFor(() => {
      expect(container.textContent).toContain('Hello docx 标题')
    })

    expect(container.querySelector('script')).toBeNull()
  })

  it('renders sample.xlsx through SheetJS', async () => {
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(
      dataUrlFromFile('sample.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    )

    const { container } = renderOffice('xlsx', 'sample.xlsx')

    await waitFor(() => {
      expect(container.textContent).toContain('Alice')
      expect(container.textContent).toContain('90')
    })
  })

  it('renders sample.pptx as a text outline', async () => {
    vi.mocked(readDesktopFileDataUrl).mockResolvedValue(
      dataUrlFromFile('sample.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation')
    )

    const { container } = renderOffice('pptx', 'sample.pptx')

    await waitFor(() => {
      expect(container.textContent).toContain('Hello PPT 第一页')
      expect(container.textContent).toContain('Slide 1')
    })
  })
})
