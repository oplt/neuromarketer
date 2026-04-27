import { Chip, type ChipProps } from '@mui/material'
import { memo, type ReactNode } from 'react'

export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'error' | 'progress'

type StatusBadgeProps = {
  label: ReactNode
  tone?: StatusTone
  icon?: ChipProps['icon']
  size?: ChipProps['size']
  variant?: ChipProps['variant']
  ariaLabel?: string
  className?: string
}

const TONE_STYLES: Record<StatusTone, { bg: string; color: string; border: string }> = {
  neutral: { bg: 'rgba(24, 34, 48, 0.06)', color: 'rgba(24, 34, 48, 0.78)', border: 'rgba(24, 34, 48, 0.16)' },
  info: { bg: 'rgba(37, 99, 235, 0.08)', color: '#1d4ed8', border: 'rgba(37, 99, 235, 0.28)' },
  success: { bg: 'rgba(16, 185, 129, 0.1)', color: '#047857', border: 'rgba(16, 185, 129, 0.28)' },
  warning: { bg: 'rgba(249, 115, 22, 0.1)', color: '#c2410c', border: 'rgba(249, 115, 22, 0.28)' },
  error: { bg: 'rgba(220, 38, 38, 0.1)', color: '#b91c1c', border: 'rgba(220, 38, 38, 0.28)' },
  progress: { bg: 'rgba(99, 102, 241, 0.1)', color: '#4338ca', border: 'rgba(99, 102, 241, 0.28)' },
}

function StatusBadgeBase({
  label,
  tone = 'neutral',
  icon,
  size = 'small',
  variant = 'outlined',
  ariaLabel,
  className,
}: StatusBadgeProps) {
  const palette = TONE_STYLES[tone]
  return (
    <Chip
      aria-label={ariaLabel || (typeof label === 'string' ? label : undefined)}
      className={className}
      icon={icon}
      label={label}
      size={size}
      sx={{
        bgcolor: palette.bg,
        color: palette.color,
        borderColor: palette.border,
        fontWeight: 600,
        '.MuiChip-icon': { color: 'inherit' },
      }}
      variant={variant}
    />
  )
}

const StatusBadge = memo(StatusBadgeBase)
export default StatusBadge
