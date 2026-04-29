import { Box, Typography } from '@mui/material'

export default function ValidationRow({ label, value }: { label: string; value: string }) {
  return (
    <Box className="analysis-stage-row">
      <Typography variant="subtitle2">{label}</Typography>
      <Typography color="text.secondary" variant="body2">
        {value}
      </Typography>
    </Box>
  )
}
