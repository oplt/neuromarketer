import {
  Box,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { memo, useMemo, type ReactNode } from 'react'
import EmptyState from './EmptyState'

export type DataTableColumn<Row> = {
  id: string
  header: ReactNode
  align?: 'left' | 'center' | 'right'
  width?: number | string
  render: (row: Row, index: number) => ReactNode
  sortable?: boolean
}

type DataTableProps<Row> = {
  rows: ReadonlyArray<Row>
  columns: ReadonlyArray<DataTableColumn<Row>>
  getRowKey: (row: Row, index: number) => string
  isLoading?: boolean
  loadingRowCount?: number
  emptyTitle?: ReactNode
  emptyDescription?: ReactNode
  ariaLabel?: string
  maxHeight?: number | string
  minWidth?: number | string
  stickyHeader?: boolean
  size?: 'small' | 'medium'
  caption?: ReactNode
}

function DataTableBase<Row>({
  rows,
  columns,
  getRowKey,
  isLoading = false,
  loadingRowCount = 4,
  emptyTitle = 'Nothing here yet',
  emptyDescription,
  ariaLabel,
  maxHeight = 480,
  minWidth = 640,
  stickyHeader = true,
  size = 'small',
  caption,
}: DataTableProps<Row>) {
  const skeletonRows = useMemo(
    () => Array.from({ length: Math.max(loadingRowCount, 1) }, (_, index) => index),
    [loadingRowCount],
  )

  if (!isLoading && rows.length === 0) {
    return <EmptyState description={emptyDescription} title={emptyTitle} />
  }

  return (
    <Box
      aria-label={ariaLabel}
      sx={{
        borderRadius: 2,
        border: '1px solid rgba(24, 34, 48, 0.08)',
        overflow: 'auto',
        maxHeight,
      }}
    >
      <Box sx={{ minWidth }}>
        <Table aria-label={ariaLabel} size={size} stickyHeader={stickyHeader}>
          {caption ? (
            <caption>
              <Typography color="text.secondary" component="span" variant="caption">
                {caption}
              </Typography>
            </caption>
          ) : null}
          <TableHead>
            <TableRow>
              {columns.map((column) => (
                <TableCell
                  align={column.align || 'left'}
                  key={column.id}
                  sx={{
                    fontWeight: 600,
                    width: column.width,
                    backgroundColor: 'rgba(248, 250, 252, 0.96)',
                  }}
                >
                  {column.header}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading
              ? skeletonRows.map((skeletonIndex) => (
                  <TableRow key={`skeleton-${skeletonIndex}`}>
                    {columns.map((column) => (
                      <TableCell align={column.align || 'left'} key={column.id}>
                        <Skeleton variant="text" width="80%" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              : rows.map((row, index) => (
                  <TableRow hover key={getRowKey(row, index)}>
                    {columns.map((column) => (
                      <TableCell align={column.align || 'left'} key={column.id}>
                        {column.render(row, index)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
          </TableBody>
        </Table>
        {!isLoading && rows.length === 0 ? (
          <Stack alignItems="center" sx={{ p: 2 }}>
            <Typography color="text.secondary" variant="body2">
              {emptyTitle}
            </Typography>
          </Stack>
        ) : null}
      </Box>
    </Box>
  )
}

const DataTable = memo(DataTableBase) as typeof DataTableBase
export default DataTable
