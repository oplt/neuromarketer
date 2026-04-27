import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import DrawerForm from './DrawerForm'

describe('DrawerForm', () => {
  it('does not render content when closed', () => {
    render(
      <DrawerForm onClose={() => {}} open={false} title="Hidden">
        <p>Hidden body</p>
      </DrawerForm>,
    )
    expect(screen.queryByText('Hidden body')).toBeNull()
  })

  it('renders the title, subtitle, and children when open', () => {
    render(
      <DrawerForm onClose={() => {}} open subtitle="Subtitle text" title="Drawer title">
        <p>Body text</p>
      </DrawerForm>,
    )
    expect(screen.getByText('Drawer title')).toBeTruthy()
    expect(screen.getByText('Subtitle text')).toBeTruthy()
    expect(screen.getByText('Body text')).toBeTruthy()
  })

  it('invokes onClose when the close icon is pressed', () => {
    const onClose = vi.fn()
    render(
      <DrawerForm onClose={onClose} open title="Drawer">
        <p>Body</p>
      </DrawerForm>,
    )
    fireEvent.click(screen.getByLabelText('Close'))
    expect(onClose).toHaveBeenCalled()
  })

  it('invokes onSubmit when the primary action is clicked inside a form', () => {
    const onSubmit = vi.fn((event) => event.preventDefault())
    render(
      <DrawerForm
        onClose={() => {}}
        onSubmit={onSubmit}
        open
        primaryActionLabel="Save"
        secondaryActionLabel="Cancel"
        title="Drawer"
      >
        <input aria-label="value" defaultValue="hello" />
      </DrawerForm>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).toHaveBeenCalled()
  })
})
