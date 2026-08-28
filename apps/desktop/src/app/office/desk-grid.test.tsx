// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'

import { DeskGrid } from './desk-grid'

function renderGrid() {
  return render(
    <I18nProvider configClient={null} initialLocale="en">
      <DeskGrid
        onAgentClick={vi.fn()}
        profiles={[
          { name: 'Alice', online: true, busy: false },
          { name: 'Bob', online: true, busy: true },
          { name: 'Carol', online: false, busy: false }
        ]}
      />
    </I18nProvider>
  )
}

describe('DeskGrid', () => {
  it('renders every profile with its name', () => {
    renderGrid()
    expect(screen.getByText('Alice')).toBeTruthy()
    expect(screen.getByText('Bob')).toBeTruthy()
    expect(screen.getByText('Carol')).toBeTruthy()
  })

  it('renders busy/offline status labels', () => {
    renderGrid()
    expect(screen.getAllByText('busy').length).toBe(1)
    expect(screen.getAllByText('offline').length).toBe(1)
    expect(screen.getAllByText('online').length).toBe(1)
  })

  it('calls onAgentClick with the profile name', () => {
    const onClick = vi.fn()
    render(
      <I18nProvider configClient={null} initialLocale="en">
        <DeskGrid
          onAgentClick={onClick}
          profiles={[{ name: 'Alice', online: true, busy: false }]}
        />
      </I18nProvider>
    )
    fireEvent.click(screen.getByText('Alice'))
    expect(onClick).toHaveBeenCalledWith(expect.objectContaining({ name: 'Alice' }))
  })
})
