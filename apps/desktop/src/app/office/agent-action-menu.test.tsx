import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AgentActionMenu } from './agent-action-menu'

vi.mock('@/i18n', () => ({
  useI18n: () => ({
    t: {
      office: {
        actions: {
          interact: 'Interact',
          interactHint: 'Visit hint',
          interactWith: (name: string) => `Interact with ${name}`,
          noOnlineTargets: 'No targets',
          viewProfile: 'View profile'
        }
      }
    }
  })
}))

afterEach(() => {
  cleanup()
})

describe('AgentActionMenu', () => {
  it('fires interact for an online target', () => {
    const onClose = vi.fn()
    const onInteract = vi.fn()

    render(
      <AgentActionMenu
        agentLabel="Alice"
        agentName="alice"
        onlineTargets={['bob']}
        onClose={onClose}
        onInteract={onInteract}
        onOpenProfile={vi.fn()}
        x={40}
        y={60}
      />
    )

    expect(screen.getByTestId('office-agent-action-menu')).toBeTruthy()
    expect(screen.getByText('Alice')).toBeTruthy()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Interact with bob' }))
    expect(onInteract).toHaveBeenCalledWith('bob')
    expect(onClose).toHaveBeenCalled()
  })

  it('shows empty targets and view profile', () => {
    const onClose = vi.fn()
    const onOpenProfile = vi.fn()

    render(
      <AgentActionMenu
        agentName="alice"
        onlineTargets={[]}
        onClose={onClose}
        onInteract={vi.fn()}
        onOpenProfile={onOpenProfile}
        x={40}
        y={60}
      />
    )

    expect(screen.getByText('No targets')).toBeTruthy()
    expect(screen.queryByText('Working')).toBeNull()
    expect(screen.queryByText('Wave')).toBeNull()

    fireEvent.click(screen.getByTestId('view-profile'))
    expect(onOpenProfile).toHaveBeenCalledWith('alice')
    expect(onClose).toHaveBeenCalled()
  })
})
