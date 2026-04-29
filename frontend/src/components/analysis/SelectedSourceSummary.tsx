import { Box, Chip, Typography } from '@mui/material'
import type { AnalysisAsset, MediaType } from '../../features/analysis/types'
import { formatFileSize } from '../../features/analysis/utils'

type SelectedSourceSummaryProps = {
  mediaType: MediaType
  selectedAsset?: AnalysisAsset
  selectedFile: File | null
  textContent: string
  textFilename: string
}

export default function SelectedSourceSummary({
  mediaType,
  selectedAsset,
  selectedFile,
  textContent,
  textFilename,
}: SelectedSourceSummaryProps) {
  if (selectedAsset && mediaType === selectedAsset.media_type && !selectedFile && !textContent.trim()) {
    return (
      <Box className="analysis-upload-card__file">
        <Box>
          <Typography variant="subtitle2">{selectedAsset.original_filename || 'Stored analysis asset'}</Typography>
          <Typography color="text.secondary" variant="body2">
            Ready from uploaded media library
            {selectedAsset.size_bytes ? ` · ${formatFileSize(selectedAsset.size_bytes)}` : ''}
          </Typography>
        </Box>
        <Chip color="success" label="Uploaded asset" size="small" variant="outlined" />
      </Box>
    )
  }

  if (mediaType === 'text') {
    return (
      <Box className="analysis-upload-card__file">
        <Box>
          <Typography variant="subtitle2">{selectedFile?.name || textFilename}</Typography>
          <Typography color="text.secondary" variant="body2">
            {selectedFile
              ? `${formatFileSize(selectedFile.size)} ready for upload`
              : textContent.trim()
                ? `${textContent.length} characters prepared for upload`
                : 'Paste text or choose a document to continue.'}
          </Typography>
        </Box>
        <Chip label={selectedFile?.type || 'Text'} size="small" variant="outlined" />
      </Box>
    )
  }

  return (
    <Box className="analysis-upload-card__file">
      <Box>
        <Typography variant="subtitle2">{selectedFile?.name || 'No file selected yet.'}</Typography>
        <Typography color="text.secondary" variant="body2">
          {selectedFile ? formatFileSize(selectedFile.size) : 'Pick or drop a file to continue.'}
        </Typography>
      </Box>
      <Chip label={selectedFile?.type || mediaType.toUpperCase()} size="small" variant="outlined" />
    </Box>
  )
}
