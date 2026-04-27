import { Box, Stack, Typography } from '@mui/material'
import { memo, type ReactNode } from 'react'

type EmptyStateProps = {
  title?: ReactNode
  description?: ReactNode
  icon?: ReactNode
  action?: ReactNode
  variant?: 'plain' | 'card'
  ariaLabel?: string
}

function EmptyStateBase({ title, description, icon, action, variant = 'card', ariaLabel }: EmptyStateProps) {
  return (
    <Box
      aria-label={ariaLabel || (typeof title === 'string' ? title : undefined)}
      className={variant === 'card' ? 'analysis-empty-state' : undefined}
      role="status"
      sx={{ p: variant === 'card' ? 2.5 : 1.25 }}
    >
      <Stack alignItems="center" spacing={1} textAlign="center">
        {icon ? <Box sx={{ color: 'text.disabled' }}>{icon}</Box> : null}
        {title ? <Typography variant="subtitle2">{title}</Typography> : null}
        {description ? (
          <Typography color="text.secondary" variant="body2">
            {description}
          </Typography>
        ) : null}
        {action}
      </Stack>
    </Box>
  )
}

const EmptyState = memo(EmptyStateBase)
export default EmptyState
