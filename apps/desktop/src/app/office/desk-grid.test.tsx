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
          { name: 'alice', label: 'Alice', online: true, busy: false },
          { name: 'bob', label: 'Bob', online: true, busy: true, currentWork: 'Energy audit' },
          { name: 'carol', label: 'Carol', online: false, busy: false }
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

  it('renders work-centric badges and a gateway-off chip when needed', () => {
    renderGrid()
    expect(screen.getAllByText('Idle').length).toBe(2)
    expect(screen.getByText('Busy')).toBeTruthy()
    expect(screen.getByText('Energy audit')).toBeTruthy()
    expect(screen.getByTestId('office-gateway-chip').textContent).toMatch(/Gateway off/i)
    expect(screen.getAllByTestId('office-status-badge').map(el => el.getAttribute('data-state'))).toEqual([
      'idle',
      'busy',
      'idle'
    ])
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
