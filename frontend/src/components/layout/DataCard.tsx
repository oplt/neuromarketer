import { Paper, Stack, Typography, type PaperProps } from '@mui/material'
import { memo, type ReactNode } from 'react'
import HelpTooltip from './HelpTooltip'

type DataCardProps = {
  title?: ReactNode
  subtitle?: ReactNode
  helpTooltip?: ReactNode
  action?: ReactNode
  children: ReactNode
  hero?: boolean
  spacing?: number
  className?: string
  paperProps?: Omit<PaperProps, 'children' | 'className' | 'elevation'>
}

function DataCardBase({
  title,
  subtitle,
  helpTooltip,
  action,
  children,
  hero = false,
  spacing = 2,
  className,
  paperProps,
}: DataCardProps) {
  return (
    <Paper
      className={`dashboard-card${hero ? ' dashboard-card--hero' : ''}${className ? ` ${className}` : ''}`}
      elevation={0}
      {...paperProps}
    >
      <Stack spacing={spacing} sx={{ minWidth: 0 }}>
        {title || subtitle || action ? (
          <Stack
            alignItems={{ xs: 'flex-start', md: 'center' }}
            direction={{ xs: 'column', md: 'row' }}
            justifyContent="space-between"
            spacing={1.5}
          >
            <Stack spacing={0.5} sx={{ minWidth: 0, flex: 1 }}>
              {title ? (
                <Stack alignItems="center" direction="row" spacing={0.5}>
                  <Typography variant="h6">{title}</Typography>
                  {helpTooltip ? <HelpTooltip title={helpTooltip} /> : null}
                </Stack>
              ) : null}
              {subtitle ? (
                <Typography color="text.secondary" variant="body2">
                  {subtitle}
                </Typography>
              ) : null}
            </Stack>
            {action ? <div>{action}</div> : null}
          </Stack>
        ) : null}
        {children}
      </Stack>
    </Paper>
  )
}

const DataCard = memo(DataCardBase)
export default DataCard
