import { Alert, LinearProgress, Stack, TextField, Typography } from '@mui/material'
import { memo } from 'react'

import type { FeedbackMessage } from '../types'
import type { RevealedApiKeyToken, RevealedInvite, RevealedWebhookSecret } from '../hooks/useAccountWorkspace'

type AccountFeedbackProps = {
  feedback: FeedbackMessage | null
  revealedInvite: RevealedInvite
  revealedRecoveryCodes: string[]
  revealedApiKeyToken: RevealedApiKeyToken
  revealedWebhookSecret: RevealedWebhookSecret
  isLoading: boolean
}

function AccountFeedbackBase({
  feedback,
  revealedInvite,
  revealedRecoveryCodes,
  revealedApiKeyToken,
  revealedWebhookSecret,
  isLoading,
}: AccountFeedbackProps) {
  return (
    <Stack spacing={2}>
      {feedback ? <Alert severity={feedback.type}>{feedback.message}</Alert> : null}
      {revealedInvite ? (
        <Alert severity="success">
          <Stack spacing={1.25}>
            <Typography variant="subtitle2">Invite created for {revealedInvite.email}</Typography>
            <TextField InputProps={{ readOnly: true }} label="Invite link" value={revealedInvite.url} />
            <TextField InputProps={{ readOnly: true }} label="Invite token" value={revealedInvite.token} />
          </Stack>
        </Alert>
      ) : null}
      {revealedRecoveryCodes.length > 0 ? (
        <Alert severity="warning">
          <Stack spacing={1.25}>
            <Typography variant="subtitle2">Recovery codes</Typography>
            <Typography variant="body2">Store these now. They are only shown once.</Typography>
            <TextField
              InputProps={{ readOnly: true }}
              label="Recovery codes"
              minRows={4}
              multiline
              value={revealedRecoveryCodes.join('\n')}
            />
          </Stack>
        </Alert>
      ) : null}
      {revealedApiKeyToken ? (
        <Alert severity="success">
          <Stack spacing={1.25}>
            <Typography variant="subtitle2">New token for {revealedApiKeyToken.label}</Typography>
            <TextField InputProps={{ readOnly: true }} value={revealedApiKeyToken.token} />
          </Stack>
        </Alert>
      ) : null}
      {revealedWebhookSecret ? (
        <Alert severity="success">
          <Stack spacing={1.25}>
            <Typography variant="subtitle2">Signing secret for {revealedWebhookSecret.label}</Typography>
            <TextField InputProps={{ readOnly: true }} value={revealedWebhookSecret.secret} />
          </Stack>
        </Alert>
      ) : null}
      {isLoading ? <LinearProgress sx={{ borderRadius: 999, height: 8 }} /> : null}
    </Stack>
  )
}

export const AccountFeedback = memo(AccountFeedbackBase)
export default AccountFeedback
