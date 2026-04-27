import { Box, Stack, Typography } from '@mui/material'
import { memo, type ReactNode } from 'react'
import HelpTooltip from './HelpTooltip'

type PageHeaderProps = {
  eyebrow?: string
  title: ReactNode
  subtitle?: ReactNode
  helpTooltip?: ReactNode
  action?: ReactNode
  align?: 'flex-start' | 'center'
  dense?: boolean
}

function PageHeaderBase({
  eyebrow,
  title,
  subtitle,
  helpTooltip,
  action,
  align = 'flex-start',
  dense = false,
}: PageHeaderProps) {
  return (
    <Stack
      alignItems={{ xs: 'stretch', md: align === 'center' ? 'center' : 'flex-end' }}
      direction={{ xs: 'column', md: 'row' }}
      justifyContent="space-between"
      spacing={dense ? 1.5 : 2.5}
    >
      <Stack alignItems={align === 'center' ? 'center' : 'flex-start'} spacing={dense ? 0.5 : 1}>
        {eyebrow ? (
          <Typography color="text.secondary" variant="overline">
            {eyebrow}
          </Typography>
        ) : null}
        <Stack alignItems="center" direction="row" spacing={0.75}>
          <Typography variant={dense ? 'h5' : 'h4'} sx={{ lineHeight: 1.2 }}>
            {title}
          </Typography>
          {helpTooltip ? <HelpTooltip title={helpTooltip} /> : null}
        </Stack>
        {subtitle ? (
          <Typography color="text.secondary" variant="body2" sx={{ maxWidth: 640 }}>
            {subtitle}
          </Typography>
        ) : null}
      </Stack>
      {action ? <Box sx={{ flexShrink: 0 }}>{action}</Box> : null}
    </Stack>
  )
}

const PageHeader = memo(PageHeaderBase)
export default PageHeader
