import InfoOutlineRounded from '@mui/icons-material/InfoOutlineRounded'
import { IconButton, Tooltip, type TooltipProps } from '@mui/material'
import { memo, type ReactNode } from 'react'

type HelpTooltipProps = {
  title: ReactNode
  ariaLabel?: string
  placement?: TooltipProps['placement']
  size?: 'small' | 'medium'
  iconColor?: string
}

function HelpTooltipBase({
  title,
  ariaLabel,
  placement = 'top',
  size = 'small',
  iconColor,
}: HelpTooltipProps) {
  return (
    <Tooltip arrow placement={placement} title={title}>
      <IconButton
        aria-label={ariaLabel || 'More information'}
        size={size}
        sx={{
          color: iconColor || 'text.secondary',
          padding: size === 'small' ? '2px' : '4px',
        }}
      >
        <InfoOutlineRounded fontSize={size === 'small' ? 'inherit' : 'small'} />
      </IconButton>
    </Tooltip>
  )
}

const HelpTooltip = memo(HelpTooltipBase)
export default HelpTooltip
