import { Stack } from '@mui/material'
import { memo, type ReactNode } from 'react'

type PageSectionProps = {
  children: ReactNode
  spacing?: number
  id?: string
}

function PageSectionBase({ children, spacing = 3, id }: PageSectionProps) {
  return (
    <Stack component="section" id={id} spacing={spacing} sx={{ minWidth: 0 }}>
      {children}
    </Stack>
  )
}

const PageSection = memo(PageSectionBase)
export default PageSection
