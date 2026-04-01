import SaveRounded from '@mui/icons-material/SaveRounded'
import SyncRounded from '@mui/icons-material/SyncRounded'
import VisibilityOffRounded from '@mui/icons-material/VisibilityOffRounded'
import VisibilityRounded from '@mui/icons-material/VisibilityRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControlLabel,
  IconButton,
  InputAdornment,
  LinearProgress,
  Paper,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'

import { apiRequest } from '../lib/api'
import type { AuthSession } from '../lib/session'

type SettingsPageProps = {
  session: AuthSession
}

type SettingGroup = {
  id: string
  label: string
  description: string
}

type SettingField = {
  key: string
  env_name: string
  group_id: string
  label: string
  value?: string | null
  value_type: string
  description?: string | null
  is_secret: boolean
  source: string
  updated_at?: string | null
}

type SettingsResponse = {
  env_file_path: string
  restart_required: boolean
  groups: SettingGroup[]
  fields: SettingField[]
}

function SettingsPage({ session }: SettingsPageProps) {
  const sessionToken = session.sessionToken
  const [settingsResponse, setSettingsResponse] = useState<SettingsResponse | null>(null)
  const [draftValues, setDraftValues] = useState<Record<string, string>>({})
  const [activeGroupId, setActiveGroupId] = useState('')
  const [hideFieldLabels, setHideFieldLabels] = useState(false)
  const [visibleSecretFields, setVisibleSecretFields] = useState<Record<string, boolean>>({})
  const [bannerMessage, setBannerMessage] = useState<{ type: 'error' | 'success' | 'info'; message: string } | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)

  const fieldsByGroup = useMemo(() => {
    const grouped = new Map<string, SettingField[]>()
    for (const field of settingsResponse?.fields || []) {
      const currentItems = grouped.get(field.group_id) || []
      currentItems.push(field)
      grouped.set(field.group_id, currentItems)
    }
    return grouped
  }, [settingsResponse])

  const dirtyKeys = useMemo(() => {
    if (!settingsResponse) {
      return []
    }
    return settingsResponse.fields
      .filter((field) => (draftValues[field.key] ?? field.value ?? '') !== (field.value ?? ''))
      .map((field) => field.key)
  }, [draftValues, settingsResponse])

  const activeGroup = useMemo(
    () => settingsResponse?.groups.find((group) => group.id === activeGroupId) ?? settingsResponse?.groups[0] ?? null,
    [activeGroupId, settingsResponse],
  )

  useEffect(() => {
    if (!settingsResponse?.groups.length) {
      if (activeGroupId) {
        setActiveGroupId('')
      }
      return
    }

    if (!settingsResponse.groups.some((group) => group.id === activeGroupId)) {
      setActiveGroupId(settingsResponse.groups[0].id)
    }
  }, [activeGroupId, settingsResponse])

  useEffect(() => {
    if (!sessionToken) {
      setBannerMessage({
        type: 'error',
        message: 'Sign out and sign in again to manage workspace settings.',
      })
      setIsLoading(false)
      return
    }

    const loadSettings = async () => {
      setIsLoading(true)
      try {
        const response = await apiRequest<SettingsResponse>('/api/v1/settings/env', { sessionToken })
        setSettingsResponse(response)
        setDraftValues(
          Object.fromEntries(response.fields.map((field) => [field.key, field.value ?? ''])),
        )
        setBannerMessage(null)
      } catch (error) {
        setBannerMessage({
          type: 'error',
          message: error instanceof Error ? error.message : 'Unable to load workspace settings.',
        })
      } finally {
        setIsLoading(false)
      }
    }

    void loadSettings()
  }, [sessionToken])

  const handleSave = async () => {
    if (!sessionToken || !settingsResponse || dirtyKeys.length === 0) {
      return
    }

    setIsSaving(true)
    try {
      await apiRequest('/api/v1/settings/env', {
        method: 'PUT',
        sessionToken,
        body: {
          entries: dirtyKeys.map((key) => ({
            key,
            value: draftValues[key] ?? '',
          })),
        },
      })

      const refreshed = await apiRequest<SettingsResponse>('/api/v1/settings/env', { sessionToken })
      setSettingsResponse(refreshed)
      setDraftValues(
        Object.fromEntries(refreshed.fields.map((field) => [field.key, field.value ?? ''])),
      )
      setBannerMessage({
        type: 'success',
        message: 'Settings saved. Backend services may need a restart before the new values take effect.',
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to save workspace settings.',
      })
    } finally {
      setIsSaving(false)
    }
  }

  const handleReload = async () => {
    if (!sessionToken) {
      return
    }
    setIsLoading(true)
    try {
      const response = await apiRequest<SettingsResponse>('/api/v1/settings/env', { sessionToken })
      setSettingsResponse(response)
      setDraftValues(
        Object.fromEntries(response.fields.map((field) => [field.key, field.value ?? ''])),
      )
      setBannerMessage({
        type: 'info',
        message: 'Reloaded settings from the backend `.env` file and persisted settings table.',
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to reload workspace settings.',
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Stack spacing={3}>
      <Paper className="dashboard-card dashboard-card--hero" elevation={0}>
        <Stack spacing={2.5}>
          <Chip color="primary" label="Workspace settings" sx={{ alignSelf: 'flex-start' }} />
          <Typography variant="h4">Manage the backend `.env` values from inside the dashboard.</Typography>
          <Typography color="text.secondary" variant="body1">
            This page reads the current backend `.env`, lets you update those values, and persists the saved state into the `settings` table.
          </Typography>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Chip label={`${settingsResponse?.fields.length || 0} variables`} variant="outlined" />
            <Chip label={`${dirtyKeys.length} unsaved`} variant="outlined" />
            {settingsResponse?.restart_required ? <Chip label="Restart required after save" variant="outlined" /> : null}
          </Stack>
        </Stack>
      </Paper>

      {bannerMessage ? <Alert severity={bannerMessage.type}>{bannerMessage.message}</Alert> : null}

      <Paper className="dashboard-card" elevation={0}>
        <Stack alignItems={{ xs: 'stretch', md: 'center' }} direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2}>
          <Box>
            <Typography variant="h6">Backend environment source</Typography>
            <Typography color="text.secondary" variant="body2">
              {settingsResponse?.env_file_path || 'Loading `.env` path…'}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button disabled={isLoading || isSaving} onClick={() => void handleReload()} startIcon={<SyncRounded />} variant="outlined">
              Reload
            </Button>
            <Button disabled={isLoading || isSaving || dirtyKeys.length === 0} onClick={() => void handleSave()} startIcon={<SaveRounded />} variant="contained">
              {isSaving ? 'Saving…' : 'Save changes'}
            </Button>
          </Stack>
        </Stack>
        {isLoading || isSaving ? <LinearProgress sx={{ mt: 2, borderRadius: 999, height: 8 }} /> : null}
      </Paper>

      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={3}>
          <Stack
            alignItems={{ xs: 'flex-start', md: 'center' }}
            direction={{ xs: 'column', md: 'row' }}
            justifyContent="space-between"
            spacing={2}
          >
            <Box>
              <Typography variant="h6">Settings groups</Typography>
              <Typography color="text.secondary" variant="body2">
                Open one configuration area at a time instead of scanning multiple containers in the same view.
              </Typography>
            </Box>
            <Stack
              alignItems={{ xs: 'flex-start', sm: 'center' }}
              direction={{ xs: 'column', sm: 'row' }}
              spacing={1.5}
            >
              <FormControlLabel
                control={
                  <Switch
                    checked={hideFieldLabels}
                    onChange={(event) => setHideFieldLabels(event.target.checked)}
                    size="small"
                  />
                }
                label="Hide field labels"
                sx={{ m: 0 }}
              />
              <Chip
                label={
                  activeGroup
                    ? `${(fieldsByGroup.get(activeGroup.id) || []).length} fields in ${activeGroup.label}`
                    : 'No settings groups'
                }
                variant="outlined"
              />
            </Stack>
          </Stack>

          {settingsResponse?.groups.length ? (
            <>
              <Tabs
                aria-label="Settings groups"
                onChange={(_, value: string) => setActiveGroupId(value)}
                scrollButtons="auto"
                sx={{
                  '& .MuiTabs-indicator': {
                    height: 3,
                    borderRadius: 999,
                  },
                }}
                value={activeGroup?.id ?? false}
                variant="scrollable"
              >
                {settingsResponse.groups.map((group) => (
                  <Tab
                    aria-controls={`settings-panel-${group.id}`}
                    id={`settings-tab-${group.id}`}
                    key={group.id}
                    label={`${group.label} (${(fieldsByGroup.get(group.id) || []).length})`}
                    value={group.id}
                  />
                ))}
              </Tabs>

              {activeGroup ? (
                <Box
                  aria-labelledby={`settings-tab-${activeGroup.id}`}
                  id={`settings-panel-${activeGroup.id}`}
                  role="tabpanel"
                  sx={{
                    borderTop: '1px solid',
                    borderColor: 'divider',
                    pt: 3,
                  }}
                >
                  <Stack spacing={3}>
                    <Box>
                      <Typography variant="h6">{activeGroup.label}</Typography>
                      <Typography color="text.secondary" variant="body2">
                        {activeGroup.description}
                      </Typography>
                    </Box>

                    <Box
                      sx={{
                        display: 'grid',
                        gap: 2,
                        gridTemplateColumns: {
                          xs: 'minmax(0, 1fr)',
                          xl: 'repeat(2, minmax(0, 1fr))',
                        },
                      }}
                    >
                      {(fieldsByGroup.get(activeGroup.id) || []).map((field) => (
                        <TextField
                          hiddenLabel={hideFieldLabels}
                          helperText={field.description || `${field.env_name} · ${field.value_type}${field.is_secret ? ' · secret' : ''}`}
                          id={`settings-field-${field.key}`}
                          key={field.key}
                          label={hideFieldLabels ? undefined : field.label}
                          minRows={field.value_type === 'json' ? 4 : undefined}
                          multiline={field.value_type === 'json'}
                          onChange={(event) =>
                            setDraftValues((current) => ({
                              ...current,
                              [field.key]: event.target.value,
                            }))
                          }
                          placeholder={hideFieldLabels ? field.label : undefined}
                          slotProps={{
                            htmlInput: hideFieldLabels
                              ? {
                                  'aria-label': field.label,
                                }
                              : undefined,
                            input:
                              field.is_secret && field.value_type !== 'json'
                                ? {
                                    endAdornment: (
                                      <InputAdornment position="end">
                                        <IconButton
                                          aria-label={
                                            visibleSecretFields[field.key]
                                              ? `Hide ${field.label}`
                                              : `Show ${field.label}`
                                          }
                                          edge="end"
                                          onClick={() =>
                                            setVisibleSecretFields((current) => ({
                                              ...current,
                                              [field.key]: !current[field.key],
                                            }))
                                          }
                                          onMouseDown={(event) => event.preventDefault()}
                                        >
                                          {visibleSecretFields[field.key] ? <VisibilityOffRounded /> : <VisibilityRounded />}
                                        </IconButton>
                                      </InputAdornment>
                                    ),
                                  }
                                : undefined,
                          }}
                          type={field.is_secret && !visibleSecretFields[field.key] ? 'password' : 'text'}
                          value={draftValues[field.key] ?? field.value ?? ''}
                        />
                      ))}
                    </Box>
                  </Stack>
                </Box>
              ) : null}
            </>
          ) : (
            <Alert severity="info">No editable settings groups are available yet.</Alert>
          )}
        </Stack>
      </Paper>
    </Stack>
  )
}

export default SettingsPage
