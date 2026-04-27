import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import TooltipInfo from './TooltipInfo'

describe('TooltipInfo', () => {
  it('renders an info icon labelled with the tooltip text by default', () => {
    render(<TooltipInfo title="What is this?" />)
    expect(screen.getByLabelText('What is this?')).toBeTruthy()
  })

  it('respects a custom aria label', () => {
    render(<TooltipInfo ariaLabel="Custom hint" title={<span>complex</span>} />)
    expect(screen.getByLabelText('Custom hint')).toBeTruthy()
  })
})
