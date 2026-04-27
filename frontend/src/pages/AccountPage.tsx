import { Box, Stack, Tab, Tabs } from '@mui/material'
import { memo, useState, type SyntheticEvent } from 'react'

import PageHeader from '../components/layout/PageHeader'
import {
  AccountFeedback,
  ApiKeysPanel,
  AuditLogTable,
  InvitesPanel,
  MembersTable,
  MfaPanel,
  OverviewPanel,
  SessionsTable,
  SsoPanel,
  WebhooksPanel,
  useAccountWorkspace,
  type AccountTabId,
} from '../features/account'
import type { AuthSession } from '../lib/session'

type AccountPageProps = {
  session: AuthSession
}

const TAB_ITEMS: ReadonlyArray<{ id: AccountTabId; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'members', label: 'Members' },
  { id: 'security', label: 'Security' },
  { id: 'api', label: 'API access' },
  { id: 'webhooks', label: 'Webhooks' },
  { id: 'audit', label: 'Audit log' },
]

function AccountPage({ session }: AccountPageProps) {
  const controller = useAccountWorkspace(session)
  const [activeTab, setActiveTab] = useState<AccountTabId>('overview')

  const handleTabChange = (_event: SyntheticEvent, value: AccountTabId) => {
    setActiveTab(value)
  }

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Account & workspace"
        subtitle="Manage members, sessions, API access, webhooks, and the audit trail."
        helpTooltip="All actions audited. Sensitive flows (rotations, MFA, SSO, role changes) require admin or owner role."
      />

      <AccountFeedback
        feedback={controller.feedbackMessage}
        revealedInvite={controller.revealedInvite}
        revealedRecoveryCodes={controller.revealedRecoveryCodes}
        revealedApiKeyToken={controller.revealedApiKeyToken}
        revealedWebhookSecret={controller.revealedWebhookSecret}
        isLoading={controller.isLoading && !controller.controlCenter}
      />

      <Box sx={{ borderBottom: '1px solid rgba(24, 34, 48, 0.08)' }}>
        <Tabs
          allowScrollButtonsMobile
          aria-label="Account workspace sections"
          onChange={handleTabChange}
          scrollButtons="auto"
          value={activeTab}
          variant="scrollable"
        >
          {TAB_ITEMS.map((tab) => (
            <Tab key={tab.id} label={tab.label} value={tab.id} />
          ))}
        </Tabs>
      </Box>

      {activeTab === 'overview' ? (
        <OverviewPanel
          session={controller.sessionInfo}
          controlCenter={controller.controlCenter}
          stats={controller.stats}
          currentUserRoleLabel={controller.currentUserRoleLabel}
          permissionSummary={controller.permissionSummary}
          isLoading={controller.isLoading}
          isRefreshing={controller.isRefreshing}
          hasSessionToken={Boolean(controller.sessionToken)}
          onRefresh={controller.refresh}
        />
      ) : null}

      {activeTab === 'members' ? (
        <Stack spacing={3}>
          <InvitesPanel
            securityOverview={controller.securityOverview}
            permissions={controller.permissions}
            email={controller.invite.email}
            onEmailChange={controller.invite.setEmail}
            role={controller.invite.role}
            onRoleChange={controller.invite.setRole}
            expiresInHours={controller.invite.expiresInHours}
            onExpiresInHoursChange={controller.invite.setExpiresInHours}
            activeMutationKey={controller.activeMutationKey}
            onCreate={controller.invite.create}
            onRevoke={controller.invite.revoke}
          />
          <MembersTable
            controlCenter={controller.controlCenter}
            permissions={controller.permissions}
            drafts={controller.member.drafts}
            onDraftsChange={controller.member.setDrafts}
            activeMutationKey={controller.activeMutationKey}
            onSaveRole={controller.member.saveRole}
          />
        </Stack>
      ) : null}

      {activeTab === 'security' ? (
        <Stack spacing={3}>
          <Box className="dashboard-grid dashboard-grid--content">
            <SessionsTable
              securityOverview={controller.securityOverview}
              activeMutationKey={controller.activeMutationKey}
              onRevoke={controller.session.revoke}
            />
            <MfaPanel
              securityOverview={controller.securityOverview}
              mfaSetup={controller.mfa.setup}
              verificationCode={controller.mfa.verificationCode}
              onVerificationCodeChange={controller.mfa.setVerificationCode}
              disableCode={controller.mfa.disableCode}
              onDisableCodeChange={controller.mfa.setDisableCode}
              disableRecoveryCode={controller.mfa.disableRecoveryCode}
              onDisableRecoveryCodeChange={controller.mfa.setDisableRecoveryCode}
              activeMutationKey={controller.activeMutationKey}
              onStart={controller.mfa.start}
              onConfirm={controller.mfa.confirm}
              onDisable={controller.mfa.disable}
              onRegenerateRecoveryCodes={controller.mfa.regenerateRecoveryCodes}
            />
          </Box>
          <SsoPanel
            securityOverview={controller.securityOverview}
            permissions={controller.permissions}
            provider={controller.sso.provider}
            onProviderChange={controller.sso.setProvider}
            enabled={controller.sso.enabled}
            onEnabledChange={controller.sso.setEnabled}
            issuerUrl={controller.sso.issuerUrl}
            onIssuerUrlChange={controller.sso.setIssuerUrl}
            entrypointUrl={controller.sso.entrypointUrl}
            onEntrypointUrlChange={controller.sso.setEntrypointUrl}
            metadataUrl={controller.sso.metadataUrl}
            onMetadataUrlChange={controller.sso.setMetadataUrl}
            audience={controller.sso.audience}
            onAudienceChange={controller.sso.setAudience}
            clientId={controller.sso.clientId}
            onClientIdChange={controller.sso.setClientId}
            clientSecret={controller.sso.clientSecret}
            onClientSecretChange={controller.sso.setClientSecret}
            scopesText={controller.sso.scopesText}
            onScopesTextChange={controller.sso.setScopesText}
            loginHintDomain={controller.sso.loginHintDomain}
            onLoginHintDomainChange={controller.sso.setLoginHintDomain}
            certificatePem={controller.sso.certificatePem}
            onCertificatePemChange={controller.sso.setCertificatePem}
            attributeMappingText={controller.sso.attributeMappingText}
            onAttributeMappingTextChange={controller.sso.setAttributeMappingText}
            activeMutationKey={controller.activeMutationKey}
            onSave={controller.sso.save}
          />
        </Stack>
      ) : null}

      {activeTab === 'api' ? (
        <ApiKeysPanel
          controlCenter={controller.controlCenter}
          permissions={controller.permissions}
          name={controller.apiKey.name}
          onNameChange={controller.apiKey.setName}
          expiresInDays={controller.apiKey.expiresInDays}
          onExpiresInDaysChange={controller.apiKey.setExpiresInDays}
          scopesText={controller.apiKey.scopesText}
          onScopesTextChange={controller.apiKey.setScopesText}
          activeMutationKey={controller.activeMutationKey}
          onCreate={controller.apiKey.create}
          onRevoke={controller.apiKey.revoke}
          onRotate={controller.apiKey.rotate}
        />
      ) : null}

      {activeTab === 'webhooks' ? (
        <WebhooksPanel
          controlCenter={controller.controlCenter}
          permissions={controller.permissions}
          url={controller.webhook.url}
          onUrlChange={controller.webhook.setUrl}
          eventsText={controller.webhook.eventsText}
          onEventsTextChange={controller.webhook.setEventsText}
          drafts={controller.webhook.drafts}
          onDraftsChange={controller.webhook.setDrafts}
          activeMutationKey={controller.activeMutationKey}
          onCreate={controller.webhook.create}
          onSave={controller.webhook.save}
          onRotateSecret={controller.webhook.rotate}
        />
      ) : null}

      {activeTab === 'audit' ? (
        <AuditLogTable controlCenter={controller.controlCenter} permissions={controller.permissions} />
      ) : null}
    </Stack>
  )
}

export default memo(AccountPage)
