import DeleteRounded from '@mui/icons-material/DeleteRounded'
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded'
import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Checkbox, Stack, Typography } from '@mui/material'
import { useState } from 'react'
import type { AnalysisAsset } from '../../features/analysis/types'
import { formatFileSize, formatTimestamp } from '../../features/analysis/utils'

type RecentUploadsProps = {
  activeAssetId: string | null
  assets: AnalysisAsset[]
  errorMessage: string | null
  hasLoaded: boolean
  isDeleting: boolean
  isLoading: boolean
  onDeleteAssets: (assetIds: string[]) => void
  onReload: () => void
  onSelectAsset: (asset: AnalysisAsset) => void
}

export default function RecentUploads(props: RecentUploadsProps) {
  return (
    <Accordion className="analysis-compact-accordion" elevation={0}>
      <AccordionSummary expandIcon={<ExpandMoreRounded />}>
        <Stack spacing={0.25}>
          <Typography variant="subtitle2">Recent uploads</Typography>
          <Typography color="text.secondary" variant="body2">
            Reuse a stored asset instead of uploading again.
          </Typography>
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <UploadedMediaLibrary {...props} />
      </AccordionDetails>
    </Accordion>
  )
}

function UploadedMediaLibrary({
  activeAssetId,
  assets,
  errorMessage,
  hasLoaded,
  isDeleting,
  isLoading,
  onDeleteAssets,
  onReload,
  onSelectAsset,
}: RecentUploadsProps) {
  const [checkedAssetIds, setCheckedAssetIds] = useState<string[]>([])
  const checkedCount = checkedAssetIds.length
  const checkedAssets = new Set(checkedAssetIds)
  const handleToggleCheckedAsset = (assetId: string) => {
    setCheckedAssetIds((current) =>
      current.includes(assetId) ? current.filter((id) => id !== assetId) : [...current, assetId],
    )
  }
  const handleDeleteCheckedAssets = () => {
    onDeleteAssets(checkedAssetIds)
    setCheckedAssetIds([])
  }

  return (
    <Stack spacing={1.5}>
      <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
        <Box>
          <Typography variant="subtitle2">Uploaded media</Typography>
          <Typography color="text.secondary" variant="body2">
            `Choose file` can only browse your local device. Reuse anything already stored in Cloudflare R2 from this list.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button
            color="error"
            disabled={checkedCount === 0 || isDeleting}
            onClick={handleDeleteCheckedAssets}
            size="small"
            startIcon={<DeleteRounded />}
            variant="outlined"
          >
            {isDeleting ? 'Deleting…' : `Delete checked${checkedCount ? ` (${checkedCount})` : ''}`}
          </Button>
          <Button onClick={onReload} size="small" variant="text">
            Refresh list
          </Button>
        </Stack>
      </Stack>

      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

      {isLoading && assets.length === 0 ? (
        <Box className="analysis-empty-state">
          <Typography color="text.secondary" variant="body2">
            Loading uploaded assets…
          </Typography>
        </Box>
      ) : null}

      {!isLoading && hasLoaded && assets.length === 0 ? (
        <Box className="analysis-empty-state">
          <Typography color="text.secondary" variant="body2">
            No uploaded media is available for this input type yet.
          </Typography>
        </Box>
      ) : null}

      {assets.length > 0 ? (
        <Box className="analysis-asset-library">
          {assets.map((asset) => {
            const isSelected = asset.id === activeAssetId
            const isReady = asset.upload_status === 'uploaded'
            return (
              <Box className={`analysis-asset-library__item ${isSelected ? 'is-selected' : ''}`} key={asset.id}>
                <Stack
                  alignItems={{ xs: 'stretch', md: 'center' }}
                  direction={{ xs: 'column', md: 'row' }}
                  justifyContent="space-between"
                  spacing={1.5}
                >
                  <Stack alignItems="flex-start" direction="row" spacing={1} sx={{ minWidth: 0 }}>
                    <Checkbox
                      checked={checkedAssets.has(asset.id)}
                      disabled={isDeleting}
                      inputProps={{ 'aria-label': `Select ${asset.original_filename || asset.object_key} for deletion` }}
                      onChange={() => handleToggleCheckedAsset(asset.id)}
                      size="small"
                      sx={{ mt: -0.75 }}
                    />
                    <Box sx={{ minWidth: 0 }}>
                      <Typography sx={{ wordBreak: 'break-word' }} variant="subtitle2">
                        {asset.original_filename || asset.object_key}
                      </Typography>
                      <Typography color="text.secondary" sx={{ wordBreak: 'break-word' }} variant="body2">
                        {formatFileSize(asset.size_bytes || 0)} · uploaded {formatTimestamp(asset.created_at)}
                      </Typography>
                      <Typography color="text.secondary" sx={{ wordBreak: 'break-word' }} variant="caption">
                        {asset.object_key}
                      </Typography>
                    </Box>
                  </Stack>
                  <Stack alignItems={{ xs: 'stretch', md: 'center' }} direction={{ xs: 'column', md: 'row' }} spacing={1}>
                    <Button
                      disabled={!isReady}
                      onClick={() => onSelectAsset(asset)}
                      size="small"
                      variant={isSelected ? 'contained' : 'outlined'}
                    >
                      {isSelected ? 'Selected' : 'Use asset'}
                    </Button>
                  </Stack>
                </Stack>
              </Box>
            )
          })}
        </Box>
      ) : null}
    </Stack>
  )
}
