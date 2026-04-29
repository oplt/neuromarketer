import { Box, Stack, Typography } from '@mui/material'

export default function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <Stack alignItems="center" direction="row" spacing={1}>
      <Box sx={{ width: 12, height: 12, borderRadius: 999, bgcolor: color }} />
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
    </Stack>
  )
}
