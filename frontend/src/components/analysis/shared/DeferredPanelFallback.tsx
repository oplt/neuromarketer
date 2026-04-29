import { LinearProgress, Paper, Stack, Typography } from '@mui/material'

export default function DeferredPanelFallback({ title }: { title: string }) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Typography variant="h6">{title}</Typography>
        <LinearProgress sx={{ borderRadius: 999, height: 8 }} />
      </Stack>
    </Paper>
  )
}
