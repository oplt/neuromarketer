import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@mui/x-charts/RadarChart', () => ({
  RadarChart: ({ series }: { series: Array<{ data: number[] }> }) => (
    <div data-testid="radar-chart">
      {series.map((s, idx) => (
        <span key={idx}>{s.data.join(',')}</span>
      ))}
    </div>
  ),
}))

import MetricsRadarCard from './MetricsRadarCard'

describe('MetricsRadarCard', () => {
  it('renders empty state when fewer than three metrics are provided', () => {
    render(
      <MetricsRadarCard
        description="Description"
        series={[{ label: 'A', metrics: [{ key: 'a', label: 'A', value: 50, unit: '/100' }] }]}
        title="Radar"
      />,
    )
    expect(screen.getByText(/Radar visualization appears/i)).toBeTruthy()
  })

  it('renders the chart when at least three metrics exist', () => {
    render(
      <MetricsRadarCard
        description="Description"
        series={[
          {
            label: 'A',
            metrics: [
              { key: 'a', label: 'A', value: 50, unit: '/100' },
              { key: 'b', label: 'B', value: 60, unit: '/100' },
              { key: 'c', label: 'C', value: 70, unit: '/100' },
            ],
          },
        ]}
        title="Radar"
      />,
    )
    expect(screen.getByTestId('radar-chart')).toBeTruthy()
    expect(screen.getByText('50,60,70')).toBeTruthy()
  })

  it('exposes description via tooltip helper icon (header is concise)', () => {
    render(
      <MetricsRadarCard
        description="Long description that should not appear inline."
        series={[]}
        title="Radar"
      />,
    )
    expect(screen.queryByText(/Long description/)).toBeNull()
    expect(screen.getByLabelText('Radar description')).toBeTruthy()
  })
})
