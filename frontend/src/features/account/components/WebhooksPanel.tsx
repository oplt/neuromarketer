import LinkRounded from '@mui/icons-material/LinkRounded'
import { Alert, Box, Button, Chip, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { memo, useCallback } from 'react'

import DataCard from '../../../components/layout/DataCard'
import HelpTooltip from '../../../components/layout/HelpTooltip'
import type { AccountControlCenter, AccountPermissions, WebhookDraft } from '../types'
import { appendDraftToken } from '../utils'
import { EmptyState } from './Shared'

type WebhooksPanelProps = {
  controlCenter: AccountControlCenter | null
  permissions?: AccountPermissions
  url: string
  onUrlChange: (value: string) => void
  eventsText: string
  onEventsTextChange: (value: string) => void
  drafts: Record<string, WebhookDraft>
  onDraftsChange: (next: (current: Record<string, WebhookDraft>) => Record<string, WebhookDraft>) => void
  activeMutationKey: string | null
  onCreate: () => void
  onSave: (webhookId: string) => void
  onRotateSecret: (webhookId: string) => void
}

function WebhooksPanelBase({
  controlCenter,
  permissions,
  url,
  onUrlChange,
  eventsText,
  onEventsTextChange,
  drafts,
  onDraftsChange,
  activeMutationKey,
  onCreate,
  onSave,
  onRotateSecret,
}: WebhooksPanelProps) {
  const canManage = Boolean(permissions?.can_manage_webhooks)
  const webhooks = controlCenter?.webhooks ?? []
  const availableEvents = controlCenter?.available_webhook_events ?? []

  const handleAppendEvent = useCallback(
    (eventName: string) => onEventsTextChange(appendDraftToken(eventsText, eventName)),
    [eventsText, onEventsTextChange],
  )

  return (
    <DataCard
      title="Webhook endpoints"
      subtitle="Outbound notifications with rotatable signing secrets."
      helpTooltip="Each endpoint receives signed POST requests for the events you subscribe to. Rotate the secret if it might have leaked."
      action={<Chip icon={<LinkRounded />} label={`${webhooks.length} endpoints`} variant="outlined" />}
    >
      <Stack spacing={2}>
        {!canManage ? (
          <Alert severity="info">Only workspace owners and admins can create or edit webhook endpoints.</Alert>
        ) : null}

        <Stack spacing={1.5}>
          <TextField
            disabled={!canManage}
            label="Webhook URL"
            onChange={(event) => onUrlChange(event.target.value)}
            placeholder="https://example.com/webhooks/neuromarketer"
            value={url}
          />
          <TextField
            disabled={!canManage}
            helperText="Comma-separated event names."
            label="Subscribed events"
            minRows={3}
            multiline
            onChange={(event) => onEventsTextChange(event.target.value)}
            value={eventsText}
          />
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            {availableEvents.map((eventName) => (
              <Chip
                key={eventName}
                label={eventName}
                onClick={() => handleAppendEvent(eventName)}
                size="small"
                variant="outlined"
              />
            ))}
          </Stack>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Button
              disabled={!canManage || !url.trim() || activeMutationKey === 'webhook-create'}
              onClick={onCreate}
              variant="contained"
            >
              {activeMutationKey === 'webhook-create' ? 'Creating…' : 'Create webhook'}
            </Button>
            <HelpTooltip title="The signing secret is displayed once at creation or rotation. Store it in your secret manager." />
          </Stack>
        </Stack>

        {webhooks.length === 0 ? (
          <EmptyState message="No webhook endpoints configured yet." />
        ) : (
          <Stack spacing={1.5}>
            {webhooks.map((webhook) => {
              const draft = drafts[webhook.id] || {
                url: webhook.url,
                eventsText: webhook.subscribed_events.join(', '),
                isActive: webhook.is_active,
              }
              return (
                <Box className="analysis-inline-summary" key={webhook.id}>
                  <Stack
                    alignItems={{ xs: 'stretch', sm: 'center' }}
                    direction={{ xs: 'column', sm: 'row' }}
                    justifyContent="space-between"
                    spacing={1.5}
                  >
                    <Typography sx={{ wordBreak: 'break-all' }} variant="subtitle2">
                      {webhook.url}
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Chip label={webhook.is_active ? 'Active' : 'Paused'} size="small" variant="outlined" />
                      <Chip label={`${webhook.subscribed_events.length} events`} size="small" variant="outlined" />
                    </Stack>
                  </Stack>
                  <TextField
                    disabled={!canManage}
                    label="Endpoint URL"
                    onChange={(event) =>
                      onDraftsChange((current) => ({
                        ...current,
                        [webhook.id]: { ...draft, url: event.target.value },
                      }))
                    }
                    value={draft.url}
                  />
                  <TextField
                    disabled={!canManage}
                    helperText="Comma-separated event names."
                    label="Subscribed events"
                    minRows={3}
                    multiline
                    onChange={(event) =>
                      onDraftsChange((current) => ({
                        ...current,
                        [webhook.id]: { ...draft, eventsText: event.target.value },
                      }))
                    }
                    value={draft.eventsText}
                  />
                  <TextField
                    disabled={!canManage}
                    label="Status"
                    onChange={(event) =>
                      onDraftsChange((current) => ({
                        ...current,
                        [webhook.id]: { ...draft, isActive: event.target.value === 'active' },
                      }))
                    }
                    select
                    value={draft.isActive ? 'active' : 'paused'}
                  >
                    <MenuItem value="active">Active</MenuItem>
                    <MenuItem value="paused">Paused</MenuItem>
                  </TextField>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                    <Button
                      disabled={!canManage || activeMutationKey === `webhook-save:${webhook.id}`}
                      onClick={() => onSave(webhook.id)}
                      variant="contained"
                    >
                      {activeMutationKey === `webhook-save:${webhook.id}` ? 'Saving…' : 'Save changes'}
                    </Button>
                    <Button
                      color="warning"
                      disabled={!canManage || activeMutationKey === `webhook-rotate:${webhook.id}`}
                      onClick={() => onRotateSecret(webhook.id)}
                      variant="outlined"
                    >
                      {activeMutationKey === `webhook-rotate:${webhook.id}` ? 'Rotating…' : 'Rotate secret'}
                    </Button>
                  </Stack>
                </Box>
              )
            })}
          </Stack>
        )}
      </Stack>
    </DataCard>
  )
}

export const WebhooksPanel = memo(WebhooksPanelBase)
export default WebhooksPanel
