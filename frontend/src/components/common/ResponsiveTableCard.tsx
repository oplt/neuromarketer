import { Box, Stack, Typography } from '@mui/material'
import { memo, type ReactNode } from 'react'

type ResponsiveTableCardProps = {
  children: ReactNode
  emptyState?: ReactNode
  isEmpty?: boolean
  maxHeight?: number | string
  minWidth?: number | string
  ariaLabel?: string
}

function ResponsiveTableCardBase({
  children,
  emptyState,
  isEmpty = false,
  maxHeight = 420,
  minWidth = 640,
  ariaLabel,
}: ResponsiveTableCardProps) {
  if (isEmpty) {
    return (
      <Box
        aria-label={ariaLabel}
        className="analysis-empty-state"
        role="status"
        sx={{ p: 2, borderRadius: 2 }}
      >
        {typeof emptyState === 'string' ? (
          <Stack alignItems="center" spacing={0.5}>
            <Typography color="text.secondary" variant="body2">
              {emptyState}
            </Typography>
          </Stack>
        ) : (
          emptyState
        )}
      </Box>
    )
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
      <Box sx={{ minWidth }}>{children}</Box>
    </Box>
  )
}

const ResponsiveTableCard = memo(ResponsiveTableCardBase)
export default ResponsiveTableCard
