import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import { Tooltip, type TooltipProps } from '@mui/material'
import { memo, type ReactNode } from 'react'

type TooltipInfoProps = {
  title: ReactNode
  ariaLabel?: string
  placement?: TooltipProps['placement']
  iconColor?: string
  fontSize?: 'inherit' | 'small' | 'medium' | 'large'
}

function TooltipInfoBase({
  title,
  ariaLabel,
  placement = 'top',
  iconColor = 'text.secondary',
  fontSize = 'small',
}: TooltipInfoProps) {
  return (
    <Tooltip arrow placement={placement} title={title}>
      <InfoOutlinedIcon
        aria-label={ariaLabel || (typeof title === 'string' ? title : 'More information')}
        fontSize={fontSize}
        sx={{ color: iconColor, cursor: 'help', verticalAlign: 'middle' }}
        tabIndex={0}
      />
    </Tooltip>
  )
}

const TooltipInfo = memo(TooltipInfoBase)
export default TooltipInfo
