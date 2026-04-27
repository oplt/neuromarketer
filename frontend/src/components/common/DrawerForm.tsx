import CloseRounded from '@mui/icons-material/CloseRounded'
import {
  Box,
  Button,
  Drawer,
  IconButton,
  Stack,
  Typography,
  type DrawerProps,
} from '@mui/material'
import { memo, type FormEvent, type ReactNode } from 'react'

type DrawerFormProps = {
  open: boolean
  onClose: () => void
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void
  title: ReactNode
  subtitle?: ReactNode
  children: ReactNode
  primaryActionLabel?: string
  primaryActionLoading?: boolean
  primaryActionDisabled?: boolean
  secondaryActionLabel?: string
  onSecondaryAction?: () => void
  width?: number | string
  anchor?: DrawerProps['anchor']
  ariaLabel?: string
  footer?: ReactNode
}

function DrawerFormBase({
  open,
  onClose,
  onSubmit,
  title,
  subtitle,
  children,
  primaryActionLabel,
  primaryActionLoading = false,
  primaryActionDisabled = false,
  secondaryActionLabel,
  onSecondaryAction,
  width = 480,
  anchor = 'right',
  ariaLabel,
  footer,
}: DrawerFormProps) {
  return (
    <Drawer
      anchor={anchor}
      onClose={onClose}
      open={open}
      PaperProps={{
        sx: {
          width: { xs: '100%', sm: width },
          maxWidth: '100vw',
          display: 'flex',
          flexDirection: 'column',
        },
      }}
    >
      <Box
        component={onSubmit ? 'form' : 'div'}
        onSubmit={onSubmit}
        aria-label={ariaLabel || (typeof title === 'string' ? title : 'Drawer form')}
        sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}
      >
        <Stack
          alignItems="center"
          direction="row"
          justifyContent="space-between"
          spacing={1.5}
          sx={{ p: 2.5, borderBottom: '1px solid rgba(24, 34, 48, 0.08)' }}
        >
          <Box>
            <Typography variant="h6">{title}</Typography>
            {subtitle ? (
              <Typography color="text.secondary" variant="body2">
                {subtitle}
              </Typography>
            ) : null}
          </Box>
          <IconButton aria-label="Close" edge="end" onClick={onClose} size="small">
            <CloseRounded />
          </IconButton>
        </Stack>

        <Box sx={{ flex: 1, overflowY: 'auto', p: 2.5 }}>
          <Stack spacing={2}>{children}</Stack>
        </Box>

        {footer || primaryActionLabel || secondaryActionLabel ? (
          <Stack
            direction="row"
            justifyContent="flex-end"
            spacing={1}
            sx={{ p: 2, borderTop: '1px solid rgba(24, 34, 48, 0.08)' }}
          >
            {footer}
            {secondaryActionLabel ? (
              <Button color="inherit" onClick={onSecondaryAction || onClose} variant="text">
                {secondaryActionLabel}
              </Button>
            ) : null}
            {primaryActionLabel ? (
              <Button
                disabled={primaryActionDisabled || primaryActionLoading}
                type={onSubmit ? 'submit' : 'button'}
                variant="contained"
              >
                {primaryActionLoading ? 'Working…' : primaryActionLabel}
              </Button>
            ) : null}
          </Stack>
        ) : null}
      </Box>
    </Drawer>
  )
}

const DrawerForm = memo(DrawerFormBase)
export default DrawerForm
