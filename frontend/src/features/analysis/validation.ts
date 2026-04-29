import type { AnalysisConfigResponse, ChannelOption, GoalTemplateOption, MediaType } from './types'
import { formatFileSize, resolveUploadMimeType } from './utils'

export function validateGoalContext({
  channel,
  goalTemplate,
  mediaType,
  objective,
  availableChannels,
  availableGoalTemplates,
}: {
  channel: string
  goalTemplate: string
  mediaType: MediaType
  objective: string
  availableChannels: ChannelOption[]
  availableGoalTemplates: GoalTemplateOption[]
}) {
  const errors: string[] = []

  if (!goalTemplate) {
    errors.push('Choose a review template before starting analysis.')
  } else if (!availableGoalTemplates.some((option) => option.value === goalTemplate)) {
    errors.push(`The selected template is not supported for ${mediaType} inputs.`)
  }

  if (!channel) {
    errors.push('Choose the target channel before starting analysis.')
  } else if (!availableChannels.some((option) => option.value === channel)) {
    errors.push(`The selected channel is not supported for ${mediaType} inputs.`)
  }

  if (objective.trim() && objective.trim().length < 16) {
    errors.push('Add a slightly more specific objective so downstream recommendations have enough context.')
  }

  return errors
}

export function validateCurrentInput({
  config,
  mediaType,
  selectedFile,
  textContent,
}: {
  config: AnalysisConfigResponse
  mediaType: MediaType
  selectedFile: File | null
  textContent: string
}) {
  const errors: string[] = []

  if (mediaType === 'text') {
    if (selectedFile) {
      if (selectedFile.size > config.max_file_size_bytes) {
        errors.push(`File size exceeds ${formatFileSize(config.max_file_size_bytes)}.`)
      }

      const selectedMimeType = resolveUploadMimeType(selectedFile)
      if (!selectedMimeType || !config.allowed_mime_types.text.includes(selectedMimeType)) {
        errors.push(`Unsupported text mime type: ${selectedMimeType || 'unknown'}.`)
      }
      return errors
    }

    const trimmedText = textContent.trim()
    if (!trimmedText) {
      errors.push('Text analysis requires pasted content or an uploaded document.')
    }
    if (trimmedText.length > config.max_text_characters) {
      errors.push(`Text analysis is limited to ${config.max_text_characters.toLocaleString()} characters.`)
    }
    return errors
  }

  if (!selectedFile) {
    errors.push(`Select a ${mediaType} file before starting the upload.`)
    return errors
  }

  if (selectedFile.size > config.max_file_size_bytes) {
    errors.push(`File size exceeds ${formatFileSize(config.max_file_size_bytes)}.`)
  }

  if (!config.allowed_mime_types[mediaType].includes(selectedFile.type)) {
    errors.push(`Unsupported ${mediaType} mime type: ${selectedFile.type || 'unknown'}.`)
  }

  return errors
}
