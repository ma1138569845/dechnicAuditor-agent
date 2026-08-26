// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'

import { KnowledgeLlmConfirm } from './llm-confirm'

afterEach(cleanup)

function renderConfirm(variant: 'default' | 'wiki', onConfirm = vi.fn()) {
  return render(
    <I18nProvider configClient={null} initialLocale="en">
      <KnowledgeLlmConfirm onClose={vi.fn()} onConfirm={onConfirm} open variant={variant} />
    </I18nProvider>
  )
}

describe('KnowledgeLlmConfirm', () => {
  it('uses the generic LLM warning when variant is default', () => {
    renderConfirm('default')

    expect(screen.getByText('This uses the LLM')).toBeTruthy()
    expect(screen.queryByText('Curate after generating')).toBeNull()
  })

  it('defaults the wiki curate option off and passes it through on confirm', () => {
    const onConfirm = vi.fn()
    renderConfirm('wiki', onConfirm)

    expect(screen.getByRole('heading', { name: 'Generate wiki' })).toBeTruthy()
    expect(screen.getByText('Curate after generating')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Generate wiki' }))
    expect(onConfirm).toHaveBeenCalledWith({ curate: false })
  })

  it('passes curate true when the wiki checkbox is checked', () => {
    const onConfirm = vi.fn()
    renderConfirm('wiki', onConfirm)

    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Generate wiki' }))

    expect(onConfirm).toHaveBeenCalledWith({ curate: true })
  })
})
