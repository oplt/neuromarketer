import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import DataTable, { type DataTableColumn } from './DataTable'

type Row = { id: string; name: string; status: string }

const COLUMNS: ReadonlyArray<DataTableColumn<Row>> = [
  { id: 'name', header: 'Name', render: (row) => row.name },
  { id: 'status', header: 'Status', render: (row) => row.status },
]

describe('DataTable', () => {
  it('renders rows when data is provided', () => {
    const rows: Row[] = [
      { id: '1', name: 'Alpha', status: 'queued' },
      { id: '2', name: 'Beta', status: 'running' },
    ]
    render(<DataTable columns={COLUMNS} getRowKey={(row) => row.id} rows={rows} />)
    expect(screen.getByText('Alpha')).toBeTruthy()
    expect(screen.getByText('Beta')).toBeTruthy()
    expect(screen.getByText('queued')).toBeTruthy()
  })

  it('renders an empty state when there are no rows', () => {
    render(
      <DataTable
        columns={COLUMNS}
        emptyDescription="No tasks yet."
        emptyTitle="Nothing pending"
        getRowKey={(row) => row.id}
        rows={[]}
      />,
    )
    expect(screen.getByText('Nothing pending')).toBeTruthy()
    expect(screen.getByText('No tasks yet.')).toBeTruthy()
  })

  it('renders skeleton rows when loading', () => {
    render(
      <DataTable
        columns={COLUMNS}
        getRowKey={(row) => row.id}
        isLoading
        loadingRowCount={3}
        rows={[]}
      />,
    )
    const tableRows = screen.getAllByRole('row')
    expect(tableRows.length).toBeGreaterThanOrEqual(3 + 1)
  })
})
