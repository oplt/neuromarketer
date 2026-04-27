import { Box, Typography } from '@mui/material'
import { memo, type ReactNode } from 'react'

type ComparisonEmptyStateProps = {
  message: ReactNode
  ariaLabel?: string
}

function ComparisonEmptyStateBase({ message, ariaLabel }: ComparisonEmptyStateProps) {
  return (
    <Box aria-label={ariaLabel} className="analysis-empty-state" role="status">
      {typeof message === 'string' ? (
        <Typography color="text.secondary" variant="body2">
          {message}
        </Typography>
      ) : (
        message
      )}
    </Box>
  )
}

const ComparisonEmptyState = memo(ComparisonEmptyStateBase)
export default ComparisonEmptyState
