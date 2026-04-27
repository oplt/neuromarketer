import { Box, Stack, Typography } from '@mui/material'
import { memo, type ReactNode } from 'react'

type DetailRowProps = {
  label: ReactNode
  value: ReactNode
  helpTooltip?: ReactNode
}

function DetailRowBase({ label, value, helpTooltip }: DetailRowProps) {
  return (
    <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={2}>
      <Stack alignItems="center" direction="row" spacing={0.5}>
        <Typography color="text.secondary" variant="body2">
          {label}
        </Typography>
        {helpTooltip}
      </Stack>
      <Typography sx={{ textAlign: 'right' }} variant="subtitle2">
        {value}
      </Typography>
    </Stack>
  )
}

export const DetailRow = memo(DetailRowBase)

function EmptyStateBase({ message }: { message: string }) {
  return (
    <Box className="analysis-empty-state" role="status">
      <Typography color="text.secondary" variant="body2">
        {message}
      </Typography>
    </Box>
  )
}

export const EmptyState = memo(EmptyStateBase)
