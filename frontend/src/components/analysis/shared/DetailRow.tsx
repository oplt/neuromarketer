import { Stack, Typography } from '@mui/material'

export default function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={2}>
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
      <Typography sx={{ textAlign: 'right', wordBreak: 'break-word' }} variant="subtitle2">
        {value}
      </Typography>
    </Stack>
  )
}
