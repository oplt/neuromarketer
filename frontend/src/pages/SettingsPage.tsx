import SaveRounded from '@mui/icons-material/SaveRounded'
import SyncRounded from '@mui/icons-material/SyncRounded'
import VisibilityOffRounded from '@mui/icons-material/VisibilityOffRounded'
import VisibilityRounded from '@mui/icons-material/VisibilityRounded'
import WarningAmberRounded from '@mui/icons-material/WarningAmberRounded'
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
import { memo, useCallback, useEffect, useMemo, useState } from 'react'

import HelpTooltip from '../components/layout/HelpTooltip'
import PageHeader from '../components/layout/PageHeader'
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

type SettingsCategory = 'workspace' | 'model' | 'admin'

const CATEGORY_LABEL: Record<SettingsCategory, string> = {
  workspace: 'Workspace',
  model: 'Model',
  admin: 'Developer / Admin',
}

const CATEGORY_TOOLTIP: Record<SettingsCategory, string> = {
  workspace: 'Day-to-day workspace and product configuration.',
  model: 'Inference, evaluation, and LLM-related configuration.',
  admin: 'Sensitive infrastructure and credential settings. Changes here may require a restart and affect all members.',
}

function classifyGroup(group: SettingGroup): SettingsCategory {
  const blob = `${group.id} ${group.label} ${group.description}`.toLowerCase()
  if (
    /(model|llm|inference|prediction|evaluator|tribe|prompt|score|scoring|ollama|openai)/.test(blob)
  ) {
    return 'model'
  }
  if (
    /(secret|token|key|credential|database|redis|broker|celery|queue|infrastructure|admin|debug|dev|backend|webhook|sso|email|smtp|s3|storage|minio|sentry|logging)/.test(
      blob,
    )
  ) {
    return 'admin'
  }
  return 'workspace'
}

function SettingsPage({ session }: SettingsPageProps) {
  const sessionToken = session.sessionToken
  const [settingsResponse, setSettingsResponse] = useState<SettingsResponse | null>(null)
  const [draftValues, setDraftValues] = useState<Record<string, string>>({})
  const [activeCategory, setActiveCategory] = useState<SettingsCategory>('workspace')
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

  const groupsByCategory = useMemo(() => {
    const out: Record<SettingsCategory, SettingGroup[]> = {
      workspace: [],
      model: [],
      admin: [],
    }
    for (const group of settingsResponse?.groups || []) {
      out[classifyGroup(group)].push(group)
    }
    return out
  }, [settingsResponse])

  const dirtyKeys = useMemo(() => {
    if (!settingsResponse) {
      return []
    }
    return settingsResponse.fields
      .filter((field) => (draftValues[field.key] ?? field.value ?? '') !== (field.value ?? ''))
      .map((field) => field.key)
  }, [draftValues, settingsResponse])

  const visibleGroups = useMemo(
    () => groupsByCategory[activeCategory] ?? [],
    [activeCategory, groupsByCategory],
  )

  const activeGroup = useMemo(
    () => visibleGroups.find((group) => group.id === activeGroupId) ?? visibleGroups[0] ?? null,
    [activeGroupId, visibleGroups],
  )

  useEffect(() => {
    if (!visibleGroups.length) {
      if (activeGroupId) {
        setActiveGroupId('')
      }
      return
    }
    if (!visibleGroups.some((group) => group.id === activeGroupId)) {
      setActiveGroupId(visibleGroups[0].id)
    }
  }, [activeGroupId, visibleGroups])

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

  const handleSave = useCallback(async () => {
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
  }, [dirtyKeys, draftValues, sessionToken, settingsResponse])

  const handleReload = useCallback(async () => {
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
        message: 'Reloaded settings from the backend.',
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to reload workspace settings.',
      })
    } finally {
      setIsLoading(false)
    }
  }, [sessionToken])

  const handleFieldChange = useCallback((key: string, value: string) => {
    setDraftValues((current) => ({ ...current, [key]: value }))
  }, [])

  const handleToggleSecret = useCallback((key: string) => {
    setVisibleSecretFields((current) => ({ ...current, [key]: !current[key] }))
  }, [])

  return (
    <Stack spacing={3}>
      <Paper className="dashboard-card dashboard-card--hero" elevation={0}>
        <Stack spacing={2.5}>
          <Chip color="primary" label="Settings" sx={{ alignSelf: 'flex-start' }} />
          <PageHeader
            dense
            title="Workspace, model, and admin settings"
            helpTooltip="Workspace and model settings are safe to edit. Developer / Admin settings can require a restart and affect all users."
            subtitle="Configure features and infrastructure for everyone in this workspace."
            action={
              <Stack direction="row" spacing={1}>
                <Button
                  disabled={isLoading || isSaving}
                  onClick={() => void handleReload()}
                  startIcon={<SyncRounded />}
                  variant="outlined"
                >
                  Reload
                </Button>
                <Button
                  disabled={isLoading || isSaving || dirtyKeys.length === 0}
                  onClick={() => void handleSave()}
                  startIcon={<SaveRounded />}
                  variant="contained"
                >
                  {isSaving ? 'Saving…' : 'Save changes'}
                </Button>
              </Stack>
            }
          />
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Chip label={`${settingsResponse?.fields.length || 0} variables`} variant="outlined" />
            <Chip
              color={dirtyKeys.length ? 'warning' : 'default'}
              label={`${dirtyKeys.length} unsaved`}
              variant="outlined"
            />
            {settingsResponse?.restart_required ? (
              <Chip
                color="warning"
                icon={<WarningAmberRounded />}
                label="Restart required after save"
                variant="outlined"
              />
            ) : null}
          </Stack>
        </Stack>
      </Paper>

      {bannerMessage ? <Alert severity={bannerMessage.type}>{bannerMessage.message}</Alert> : null}

      {isLoading || isSaving ? <LinearProgress sx={{ borderRadius: 999, height: 6 }} /> : null}

      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={3}>
          <Stack
            alignItems={{ xs: 'flex-start', md: 'center' }}
            direction={{ xs: 'column', md: 'row' }}
            justifyContent="space-between"
            spacing={2}
          >
            <Tabs
              aria-label="Settings categories"
              onChange={(_, value: SettingsCategory) => setActiveCategory(value)}
              sx={{ '& .MuiTabs-indicator': { height: 3, borderRadius: 999 } }}
              value={activeCategory}
            >
              {(['workspace', 'model', 'admin'] as const).map((category) => (
                <Tab
                  key={category}
                  label={
                    <Stack alignItems="center" direction="row" spacing={0.5}>
                      {category === 'admin' ? (
                        <WarningAmberRounded fontSize="inherit" sx={{ color: 'warning.main' }} />
                      ) : null}
                      <span>{CATEGORY_LABEL[category]}</span>
                      <HelpTooltip title={CATEGORY_TOOLTIP[category]} />
                    </Stack>
                  }
                  value={category}
                />
              ))}
            </Tabs>

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
          </Stack>

          {activeCategory === 'admin' ? (
            <Alert
              icon={<WarningAmberRounded fontSize="inherit" />}
              severity="warning"
              variant="outlined"
            >
              Developer / Admin settings change infrastructure or credentials. Most edits require a restart and affect every member.
            </Alert>
          ) : null}

          {visibleGroups.length ? (
            <>
              <Tabs
                aria-label="Settings groups"
                onChange={(_, value: string) => setActiveGroupId(value)}
                scrollButtons="auto"
                sx={{ '& .MuiTabs-indicator': { height: 3, borderRadius: 999 } }}
                value={activeGroup?.id ?? false}
                variant="scrollable"
              >
                {visibleGroups.map((group) => (
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
                  sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 3 }}
                >
                  <Stack spacing={3}>
                    <Box>
                      <Stack alignItems="center" direction="row" spacing={0.5}>
                        <Typography variant="h6">{activeGroup.label}</Typography>
                        <HelpTooltip title={activeGroup.description} />
                      </Stack>
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
                        <SettingFieldInput
                          key={field.key}
                          field={field}
                          hideFieldLabels={hideFieldLabels}
                          onChange={handleFieldChange}
                          onToggleSecret={handleToggleSecret}
                          showSecret={!!visibleSecretFields[field.key]}
                          value={draftValues[field.key] ?? field.value ?? ''}
                        />
                      ))}
                    </Box>
                  </Stack>
                </Box>
              ) : null}
            </>
          ) : (
            <Alert severity="info">
              No {CATEGORY_LABEL[activeCategory].toLowerCase()} settings are available in this workspace.
            </Alert>
          )}
        </Stack>
      </Paper>
    </Stack>
  )
}

type SettingFieldInputProps = {
  field: SettingField
  value: string
  showSecret: boolean
  hideFieldLabels: boolean
  onChange: (key: string, value: string) => void
  onToggleSecret: (key: string) => void
}

function SettingFieldInputBase({
  field,
  value,
  showSecret,
  hideFieldLabels,
  onChange,
  onToggleSecret,
}: SettingFieldInputProps) {
  const helperText = field.description || `${field.env_name} · ${field.value_type}${field.is_secret ? ' · secret' : ''}`

  return (
    <TextField
      hiddenLabel={hideFieldLabels}
      helperText={helperText}
      id={`settings-field-${field.key}`}
      label={hideFieldLabels ? undefined : field.label}
      minRows={field.value_type === 'json' ? 4 : undefined}
      multiline={field.value_type === 'json'}
      onChange={(event) => onChange(field.key, event.target.value)}
      placeholder={hideFieldLabels ? field.label : undefined}
      slotProps={{
        htmlInput: hideFieldLabels ? { 'aria-label': field.label } : undefined,
        input:
          field.is_secret && field.value_type !== 'json'
            ? {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      aria-label={showSecret ? `Hide ${field.label}` : `Show ${field.label}`}
                      edge="end"
                      onClick={() => onToggleSecret(field.key)}
                      onMouseDown={(event) => event.preventDefault()}
                    >
                      {showSecret ? <VisibilityOffRounded /> : <VisibilityRounded />}
                    </IconButton>
                  </InputAdornment>
                ),
              }
            : undefined,
      }}
      type={field.is_secret && !showSecret ? 'password' : 'text'}
      value={value}
    />
  )
}

const SettingFieldInput = memo(SettingFieldInputBase)

export default SettingsPage
