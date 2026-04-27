import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Stack,
  Typography,
} from '@mui/material'
import { memo, useState, type ReactNode, type SyntheticEvent } from 'react'

type AdvancedDetailsProps = {
  title: ReactNode
  description?: ReactNode
  children: ReactNode
  defaultExpanded?: boolean
  variant?: 'default' | 'caution' | 'admin'
  badge?: ReactNode
  id?: string
}

function AdvancedDetailsBase({
  title,
  description,
  children,
  defaultExpanded = false,
  variant = 'default',
  badge,
  id,
}: AdvancedDetailsProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const summaryColor =
    variant === 'caution'
      ? 'warning.main'
      : variant === 'admin'
        ? 'error.main'
        : 'text.primary'

  const handleExpandedChange = (_event: SyntheticEvent, value: boolean) => {
    setIsExpanded(value)
  }

  return (
    <Accordion
      disableGutters
      elevation={0}
      expanded={isExpanded}
      id={id}
      onChange={handleExpandedChange}
      square
      sx={{
        background: 'rgba(248, 250, 252, 0.6)',
        border: '1px solid rgba(24, 34, 48, 0.08)',
        borderRadius: 3,
        overflow: 'hidden',
        '&::before': { display: 'none' },
      }}
    >
      <AccordionSummary
        aria-controls={id ? `${id}-content` : undefined}
        expandIcon={<ExpandMoreRounded />}
        id={id ? `${id}-header` : undefined}
        sx={{
          minHeight: 48,
          px: 2,
          '& .MuiAccordionSummary-content': { my: 1.25 },
        }}
      >
        <Stack alignItems="center" direction="row" spacing={1.25} sx={{ width: '100%' }}>
          <Stack spacing={0.25} sx={{ minWidth: 0, flex: 1 }}>
            <Typography color={summaryColor} variant="subtitle2">
              {title}
            </Typography>
            {description ? (
              <Typography color="text.secondary" variant="caption">
                {description}
              </Typography>
            ) : null}
          </Stack>
          {badge}
        </Stack>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0, pb: 2, px: 2 }}>{children}</AccordionDetails>
    </Accordion>
  )
}

const AdvancedDetails = memo(AdvancedDetailsBase)
export default AdvancedDetails
