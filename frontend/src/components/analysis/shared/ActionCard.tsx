import { Box, Button, Chip, Stack, Typography } from '@mui/material'
import type { ReactElement } from 'react'

type ActionCardProps = {
  ctaLabel: string
  description: string
  disabled: boolean
  icon: ReactElement
  label: string
  onClick: () => void
  testId: string
}

export default function ActionCard({
  ctaLabel,
  description,
  disabled,
  icon,
  label,
  onClick,
  testId,
}: ActionCardProps) {
  return (
    <Box className={`analysis-action-card ${disabled ? 'is-disabled' : ''}`}>
      <Stack spacing={1.5}>
        <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1.5}>
          <Chip icon={icon} label={label} size="small" variant="outlined" />
        </Stack>
        <Typography color="text.secondary" variant="body2">
          {description}
        </Typography>
        <Button data-testid={testId} disabled={disabled} onClick={onClick} variant="contained">
          {ctaLabel}
        </Button>
      </Stack>
    </Box>
  )
}
