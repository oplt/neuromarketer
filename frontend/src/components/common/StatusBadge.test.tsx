import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import StatusBadge from './StatusBadge'

describe('StatusBadge', () => {
  it('renders the label text', () => {
    render(<StatusBadge label="Queued" />)
    expect(screen.getByText('Queued')).toBeTruthy()
  })

  it('exposes an aria label that defaults to the string label', () => {
    render(<StatusBadge label="Failed" tone="error" />)
    expect(screen.getByLabelText('Failed')).toBeTruthy()
  })

  it('respects an explicit aria label override', () => {
    render(<StatusBadge ariaLabel="Status: ok" label={<span>OK</span>} tone="success" />)
    expect(screen.getByLabelText('Status: ok')).toBeTruthy()
  })

  it('applies tone-specific styles without throwing for each tone', () => {
    const tones = ['neutral', 'info', 'success', 'warning', 'error', 'progress'] as const
    for (const tone of tones) {
      const { unmount } = render(<StatusBadge label={tone} tone={tone} />)
      expect(screen.getByText(tone)).toBeTruthy()
      unmount()
    }
  })
})
