import { Box, Skeleton, Typography } from '@mui/material'
import { scoreToColor } from '../../../features/analysis/resultRendering'

type ScoreGaugeProps = {
  value: number
  label: string
  isReady: boolean
  size?: number
}

export default function ScoreGauge({ value, label, isReady, size = 76 }: ScoreGaugeProps) {
  const strokeWidth = 6
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const filled = (Math.max(0, Math.min(100, value)) / 100) * circumference
  const color = scoreToColor(value)

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.5 }}>
      <Box sx={{ position: 'relative', width: size, height: size }}>
        <svg
          aria-hidden="true"
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          style={{ transform: 'rotate(-90deg)' }}
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="rgba(24,34,48,0.08)"
            strokeWidth={strokeWidth}
          />
          {isReady && (
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={color}
              strokeWidth={strokeWidth}
              strokeDasharray={`${filled} ${circumference}`}
              strokeLinecap="round"
            />
          )}
        </svg>
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {isReady ? (
            <Typography sx={{ fontWeight: 700, fontSize: 14, lineHeight: 1, color }}>
              {Math.round(value)}
            </Typography>
          ) : (
            <Skeleton width={28} height={16} sx={{ transform: 'none' }} />
          )}
        </Box>
      </Box>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ textAlign: 'center', lineHeight: 1.2, maxWidth: size }}
      >
        {label}
      </Typography>
    </Box>
  )
}
