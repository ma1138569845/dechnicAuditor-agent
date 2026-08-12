import { cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'

import { AiEditToolbar } from './ai-edit-toolbar'

const slot = (container: HTMLElement, name: string) => container.querySelector(`[data-slot="${name}"]`)

function renderToolbar({ onSubmit = vi.fn(), onDismiss = vi.fn(), onPromptingChange = vi.fn() } = {}) {
  const rendered = render(
    <I18nProvider configClient={null}>
      <AiEditToolbar
        anchor={{ x: 10, y: 20 }}
        onDismiss={onDismiss}
        onPromptingChange={onPromptingChange}
        onSubmit={onSubmit}
      />
    </I18nProvider>
  )

  return { ...rendered, onDismiss, onPromptingChange, onSubmit }
}

describe('AiEditToolbar', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders the collapsed "AI edit" pill', () => {
    const { container } = renderToolbar()

    expect(slot(container, 'ai-edit-open')).toBeTruthy()
    expect(slot(container, 'ai-edit-prompt-input')).toBeNull()
  })

  it('opens the prompt box on click', () => {
    const { container } = renderToolbar()

    fireEvent.click(slot(container, 'ai-edit-open')!)

    expect(slot(container, 'ai-edit-prompt-input')).toBeTruthy()
  })

  it('submits the typed prompt via the confirm button', () => {
    const { container, onSubmit } = renderToolbar()

    fireEvent.click(slot(container, 'ai-edit-open')!)
    fireEvent.change(slot(container, 'ai-edit-prompt-input')!, {
      target: { value: 'make it more formal' }
    })
    fireEvent.click(slot(container, 'ai-edit-confirm')!)

    expect(onSubmit).toHaveBeenCalledWith('make it more formal')
  })

  it('keeps the confirm button disabled while the prompt is empty', () => {
    const { container } = renderToolbar()

    fireEvent.click(slot(container, 'ai-edit-open')!)

    const confirm = slot(container, 'ai-edit-confirm') as HTMLButtonElement

    expect(confirm.disabled).toBe(true)
  })

  it('dismisses via ESC', () => {
    const { onDismiss } = renderToolbar()

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(onDismiss).toHaveBeenCalled()
  })

  it('dismisses on an outside mousedown', () => {
    const { onDismiss } = renderToolbar()

    fireEvent.mouseDown(document.body)

    expect(onDismiss).toHaveBeenCalled()
  })

  it('does not dismiss when clicking the toolbar itself', () => {
    const { container, onDismiss } = renderToolbar()

    fireEvent.mouseDown(slot(container, 'ai-edit-toolbar')!)

    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('reports the prompt-box state to the parent when it opens', () => {
    const { container, onPromptingChange } = renderToolbar()

    expect(onPromptingChange).toHaveBeenCalledWith(false)

    fireEvent.click(slot(container, 'ai-edit-open')!)

    expect(onPromptingChange).toHaveBeenCalledWith(true)
  })

  it('resets the prompt-box latch to false on unmount', () => {
    const { container, onPromptingChange, unmount } = renderToolbar()

    fireEvent.click(slot(container, 'ai-edit-open')!)
    unmount()

    expect(onPromptingChange).toHaveBeenLastCalledWith(false)
  })
})
