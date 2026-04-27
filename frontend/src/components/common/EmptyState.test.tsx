import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import EmptyState from './EmptyState'

describe('EmptyState', () => {
  it('renders a title and description when provided', () => {
    render(<EmptyState description="Try again later." title="Nothing here" />)
    expect(screen.getByText('Nothing here')).toBeTruthy()
    expect(screen.getByText('Try again later.')).toBeTruthy()
  })

  it('falls back to status role for screen readers', () => {
    render(<EmptyState title="Empty" />)
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('renders the action region when provided', () => {
    render(
      <EmptyState
        action={<button type="button">Refresh</button>}
        title="Empty"
      />,
    )
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeTruthy()
  })
})
