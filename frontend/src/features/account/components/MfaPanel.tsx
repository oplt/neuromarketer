import { Alert, Button, Chip, Stack, TextField } from '@mui/material'
import { memo } from 'react'

import DataCard from '../../../components/layout/DataCard'
import HelpTooltip from '../../../components/layout/HelpTooltip'
import type { AccountSecurityOverview, MfaSetupResponse } from '../types'
import { formatDateTime } from '../utils'
import { DetailRow } from './Shared'

type MfaPanelProps = {
  securityOverview: AccountSecurityOverview | null
  mfaSetup: MfaSetupResponse | null
  verificationCode: string
  onVerificationCodeChange: (value: string) => void
  disableCode: string
  onDisableCodeChange: (value: string) => void
  disableRecoveryCode: string
  onDisableRecoveryCodeChange: (value: string) => void
  activeMutationKey: string | null
  onStart: () => void
  onConfirm: () => void
  onDisable: () => void
  onRegenerateRecoveryCodes: () => void
}

function MfaPanelBase({
  securityOverview,
  mfaSetup,
  verificationCode,
  onVerificationCodeChange,
  disableCode,
  onDisableCodeChange,
  disableRecoveryCode,
  onDisableRecoveryCodeChange,
  activeMutationKey,
  onStart,
  onConfirm,
  onDisable,
  onRegenerateRecoveryCodes,
}: MfaPanelProps) {
  const mfa = securityOverview?.mfa
  const hasDisableInput = disableCode.trim() !== '' || disableRecoveryCode.trim() !== ''

  return (
    <DataCard
      title="Multi-factor authentication"
      subtitle="TOTP enrollment with one-time recovery codes."
      helpTooltip="Recovery codes are only displayed once. Store them in a secret manager to recover access if you lose the authenticator."
    >
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          <Chip
            color={mfa?.is_enabled ? 'primary' : 'default'}
            label={mfa?.is_enabled ? 'MFA enabled' : 'MFA not enabled'}
            variant={mfa?.is_enabled ? 'filled' : 'outlined'}
          />
          <Chip
            label={mfa ? `${mfa.recovery_codes_remaining} recovery codes` : 'Recovery codes unavailable'}
            variant="outlined"
          />
        </Stack>
        <Stack spacing={1.1}>
          <DetailRow label="Method" value={mfa?.method_type || 'totp'} />
          <DetailRow label="Last used" value={mfa?.last_used_at ? formatDateTime(mfa.last_used_at) : 'Not recorded'} />
          <DetailRow label="Pending setup" value={mfa?.pending_setup ? 'Awaiting confirmation' : 'No'} />
        </Stack>
        {mfaSetup ? (
          <Alert severity="info">
            <Stack spacing={1.25}>
              <TextField InputProps={{ readOnly: true }} label="Manual secret" value={mfaSetup.secret} />
              <TextField InputProps={{ readOnly: true }} label="OTPAuth URI" value={mfaSetup.otpauth_uri} />
            </Stack>
          </Alert>
        ) : null}
        <TextField
          helperText="Six-digit code from your authenticator app."
          label="Verification code"
          onChange={(event) => onVerificationCodeChange(event.target.value)}
          value={verificationCode}
        />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Button disabled={activeMutationKey === 'mfa-setup'} onClick={onStart} variant="contained">
            {activeMutationKey === 'mfa-setup' ? 'Preparing…' : 'Start MFA setup'}
          </Button>
          <Button
            disabled={!mfaSetup || !verificationCode.trim() || activeMutationKey === 'mfa-confirm'}
            onClick={onConfirm}
            variant="outlined"
          >
            {activeMutationKey === 'mfa-confirm' ? 'Confirming…' : 'Confirm setup'}
          </Button>
        </Stack>

        <Stack direction="row" alignItems="center" spacing={0.5}>
          <Stack spacing={0.25} sx={{ flex: 1 }}>
            <TextField
              label="Disable / regenerate verification code"
              onChange={(event) => onDisableCodeChange(event.target.value)}
              value={disableCode}
            />
          </Stack>
          <HelpTooltip title="Provide either the active TOTP code or a recovery code to disable MFA or regenerate codes." />
        </Stack>
        <TextField
          label="Recovery code"
          onChange={(event) => onDisableRecoveryCodeChange(event.target.value)}
          value={disableRecoveryCode}
        />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Button
            disabled={!hasDisableInput || activeMutationKey === 'mfa-recovery'}
            onClick={onRegenerateRecoveryCodes}
            variant="outlined"
          >
            {activeMutationKey === 'mfa-recovery' ? 'Rotating…' : 'Regenerate recovery codes'}
          </Button>
          <Button
            color="warning"
            disabled={!hasDisableInput || activeMutationKey === 'mfa-disable'}
            onClick={onDisable}
            variant="outlined"
          >
            {activeMutationKey === 'mfa-disable' ? 'Disabling…' : 'Disable MFA'}
          </Button>
        </Stack>
      </Stack>
    </DataCard>
  )
}

export const MfaPanel = memo(MfaPanelBase)
export default MfaPanel
