import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import type { AuthSession } from '../lib/session'
type AuthField = {
  id: string
  name: string
  label: string
  type: string
  placeholder: string
  autoComplete: string
}

type SignInValues = {
  email: string
  password: string
}

type SignUpValues = {
  fullName: string
  email: string
  password: string
}

type AuthFeedback = {
  type: 'success' | 'error' | 'info'
  message: string
}

type HomePageProps = {
  onSignedIn: (session: AuthSession) => void
}

type AuthResponse = {
  detail?: string
  error?: {
    message?: string
  }
  message?: string
  user?: {
    id?: string
    email: string
    full_name?: string | null
  }
  organization?: {
    id?: string
    name?: string
    slug?: string
  } | null
  default_project?: {
    id?: string
    name?: string
  } | null
  session_token?: string | null
  requires_mfa?: boolean
  mfa_challenge_token?: string | null
  available_mfa_methods?: string[]
}

type InvitePreview = {
  workspace_name: string
  workspace_slug: string
  email: string
  role: 'owner' | 'admin' | 'member' | 'viewer'
  expires_at: string
}

type MfaChallengeState = {
  token: string
  email: string
  fullName: string
  organizationName?: string
  organizationSlug?: string
  defaultProjectId?: string
  defaultProjectName?: string
}

const signInFields: AuthField[] = [
  {
    id: 'signin-email',
    name: 'email',
    label: 'Email address',
    type: 'email',
    placeholder: 'Email',
    autoComplete: 'email',
  },
  {
    id: 'signin-password',
    name: 'password',
    label: 'Password',
    type: 'password',
    placeholder: 'Password',
    autoComplete: 'current-password',
  },
]

const signUpFields: AuthField[] = [
  {
    id: 'signup-name',
    name: 'fullName',
    label: 'Full name',
    type: 'text',
    placeholder: 'Name',
    autoComplete: 'name',
  },
  {
    id: 'signup-email',
    name: 'email',
    label: 'Email address',
    type: 'email',
    placeholder: 'Email',
    autoComplete: 'email',
  },
  {
    id: 'signup-password',
    name: 'password',
    label: 'Password',
    type: 'password',
    placeholder: 'Password',
    autoComplete: 'new-password',
  },
]

const productHighlights = [
  'Score creative on attention, memory, and conversion proxies before launch',
  'Compare versions side-by-side and pick a winner with confidence',
  'Generate prioritized recommendations your marketing team can ship',
]

function HomePage({ onSignedIn }: HomePageProps) {
  const [isSignUpActive, setIsSignUpActive] = useState(false)
  const [signInValues, setSignInValues] = useState<SignInValues>({
    email: '',
    password: '',
  })
  const [signUpValues, setSignUpValues] = useState<SignUpValues>({
    fullName: '',
    email: '',
    password: '',
  })
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [authFeedback, setAuthFeedback] = useState<AuthFeedback | null>(null)
  const [inviteToken, setInviteToken] = useState('')
  const [invitePreview, setInvitePreview] = useState<InvitePreview | null>(null)
  const [mfaChallenge, setMfaChallenge] = useState<MfaChallengeState | null>(null)
  const [mfaCode, setMfaCode] = useState('')
  const [mfaRecoveryCode, setMfaRecoveryCode] = useState('')
  const [showHowItWorks, setShowHowItWorks] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }
    const params = new URLSearchParams(window.location.search)
    const token = params.get('invite') || ''
    if (!token) {
      setInviteToken('')
      setInvitePreview(null)
      return
    }
    setInviteToken(token)
    setIsSignUpActive(true)
    let isCancelled = false
    void fetch(`/api/v1/auth/invites/preview?token=${encodeURIComponent(token)}`)
      .then(async (response) => {
        const body = (await response.json().catch(() => null)) as InvitePreview | { detail?: string } | null
        if (!response.ok) {
          throw new Error(body && 'detail' in body ? body.detail || 'Unable to load invite.' : 'Unable to load invite.')
        }
        if (isCancelled || !body || !('email' in body)) {
          return
        }
        setInvitePreview(body)
        setSignUpValues((current) => ({
          ...current,
          email: body.email,
        }))
      })
      .catch((error) => {
        if (isCancelled) {
          return
        }
        setInviteToken('')
        setInvitePreview(null)
        setAuthFeedback({
          type: 'error',
          message: error instanceof Error ? error.message : 'Unable to load invite.',
        })
      })
    return () => {
      isCancelled = true
    }
  }, [])

  const handleSignInChange = (fieldName: string, value: string) => {
    setSignInValues((current) => ({
      ...current,
      [fieldName]: value,
    }))
  }

  const handleSignUpChange = (fieldName: string, value: string) => {
    setSignUpValues((current) => ({
      ...current,
      [fieldName]: value,
    }))
  }

  const handleSubmit = async (
    mode: 'signin' | 'signup',
    event: FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault()
    setAuthFeedback(null)

    setIsSubmitting(true)

    try {
      const endpoint =
        mode === 'signup'
          ? inviteToken
            ? '/api/v1/auth/invites/accept'
            : '/api/v1/auth/signup'
          : '/api/v1/auth/signin'
      const payload =
        mode === 'signup'
          ? inviteToken
            ? {
                invite_token: inviteToken,
                full_name: signUpValues.fullName.trim(),
                password: signUpValues.password,
              }
            : {
                full_name: signUpValues.fullName.trim(),
                email: signUpValues.email.trim(),
                password: signUpValues.password,
              }
          : {
              email: signInValues.email.trim(),
              password: signInValues.password,
            }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      const body = (await response.json().catch(() => null)) as AuthResponse | null
      if (!response.ok) {
        throw new Error(body?.error?.message || body?.detail || 'Request failed.')
      }

      if (mode === 'signup' && !body?.session_token && !body?.requires_mfa) {
        setAuthFeedback({
          type: 'success',
          message: body?.message || 'Account created successfully. Sign in to open your dashboard.',
        })
        setSignInValues({
          email: body?.user?.email || signUpValues.email.trim(),
          password: '',
        })
        setSignUpValues({
          fullName: '',
          email: '',
          password: '',
        })
        setIsSignUpActive(false)
        return
      }

      if (body?.requires_mfa && body?.mfa_challenge_token) {
        setMfaChallenge({
          token: body.mfa_challenge_token,
          email: body?.user?.email || signInValues.email.trim() || signUpValues.email.trim(),
          fullName: body?.user?.full_name || signUpValues.fullName || 'Workspace member',
          organizationName: body?.organization?.name,
          organizationSlug: body?.organization?.slug,
          defaultProjectId: body?.default_project?.id,
          defaultProjectName: body?.default_project?.name,
        })
        setMfaCode('')
        setMfaRecoveryCode('')
        setAuthFeedback({
          type: 'info',
          message: body.message || 'Enter the MFA code from your authenticator app to continue.',
        })
        setIsSignUpActive(false)
        return
      }

      onSignedIn({
        userId: body?.user?.id,
        email: body?.user?.email || signInValues.email.trim(),
        fullName: body?.user?.full_name || 'Workspace member',
        organizationName: body?.organization?.name,
        organizationSlug: body?.organization?.slug,
        defaultProjectId: body?.default_project?.id,
        defaultProjectName: body?.default_project?.name,
        sessionToken: body?.session_token || undefined,
      })
      setSignInValues({
        email: signInValues.email.trim(),
        password: '',
      })
      setMfaChallenge(null)
    } catch (error) {
      setAuthFeedback({
        type: 'error',
        message:
          error instanceof Error
            ? error.message
            : 'Unable to complete the request. Please try again.',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleMfaVerify = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!mfaChallenge) {
      return
    }

    setAuthFeedback(null)
    setIsSubmitting(true)
    try {
      const response = await fetch('/api/v1/auth/mfa/verify', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          challenge_token: mfaChallenge.token,
          code: mfaCode.trim() || null,
          recovery_code: mfaRecoveryCode.trim() || null,
        }),
      })
      const body = (await response.json().catch(() => null)) as AuthResponse | null
      if (!response.ok) {
        throw new Error(body?.error?.message || body?.detail || 'Request failed.')
      }
      onSignedIn({
        userId: body?.user?.id,
        email: body?.user?.email || mfaChallenge.email,
        fullName: body?.user?.full_name || mfaChallenge.fullName,
        organizationName: body?.organization?.name || mfaChallenge.organizationName,
        organizationSlug: body?.organization?.slug || mfaChallenge.organizationSlug,
        defaultProjectId: body?.default_project?.id || mfaChallenge.defaultProjectId,
        defaultProjectName: body?.default_project?.name || mfaChallenge.defaultProjectName,
        sessionToken: body?.session_token || undefined,
      })
      setMfaChallenge(null)
      setMfaCode('')
      setMfaRecoveryCode('')
      setSignInValues((current) => ({ ...current, password: '' }))
    } catch (error) {
      setAuthFeedback({
        type: 'error',
        message:
          error instanceof Error
            ? error.message
            : 'Unable to verify the MFA challenge. Please try again.',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="landing-page">
      <div className="landing-page__grain" />
      <div className="landing-page__halo landing-page__halo--blue" />
      <div className="landing-page__halo landing-page__halo--mint" />

      <div className="landing-page__layout">
        <section className="landing-page__hero">
          <div className="landing-page__brand-row">
            <span className="landing-page__brand">NeuroMarketer</span>
            <span className="landing-page__status">Creative intelligence for launch teams</span>
          </div>

          <div className="landing-page__copy">
            <span className="landing-page__eyebrow">Predict creative performance before spend starts</span>
            <h1>Decide which creative to ship — backed by attention, memory, and conversion signals.</h1>
            <ul className="landing-page__highlights">
              {productHighlights.map((highlight) => (
                <li key={highlight}>{highlight}</li>
              ))}
            </ul>
            <button
              aria-expanded={showHowItWorks}
              className="landing-page__more-toggle"
              onClick={() => setShowHowItWorks((current) => !current)}
              type="button"
            >
              {showHowItWorks ? 'Hide how it works' : 'How it works'}
            </button>
            {showHowItWorks ? (
              <ol className="landing-page__how-it-works">
                <li>Upload a video, image, audio, or text creative.</li>
                <li>Run multimodal scoring with a single click.</li>
                <li>Open compare to rank versions and export recommendations.</li>
              </ol>
            ) : null}
          </div>
        </section>

        <aside className="landing-page__auth-column">
          <div className="landing-page__auth-stack">
            {authFeedback ? (
              <div className={`codepen-auth__feedback codepen-auth__feedback--${authFeedback.type}`}>
                {authFeedback.message}
              </div>
            ) : null}

            <div className={`codepen-auth ${isSignUpActive ? 'right-panel-active' : ''}`}>
              <div className="codepen-auth__form-container codepen-auth__sign-up-container">
                {invitePreview ? (
                  <InviteAcceptForm
                    invitePreview={invitePreview}
                    isSubmitting={isSubmitting}
                    onFieldChange={handleSignUpChange}
                    onSubmit={(event) => handleSubmit('signup', event)}
                    values={signUpValues}
                  />
                ) : (
                  <AuthForm
                    buttonLabel="Sign Up"
                    fields={signUpFields}
                    isSubmitting={isSubmitting}
                    onFieldChange={handleSignUpChange}
                    onSubmit={(event) => handleSubmit('signup', event)}
                    title="Create Account"
                    values={signUpValues}
                  />
                )}
              </div>

              <div className="codepen-auth__form-container codepen-auth__sign-in-container">
                {mfaChallenge ? (
                  <MfaChallengeForm
                    code={mfaCode}
                    email={mfaChallenge.email}
                    isSubmitting={isSubmitting}
                    onCodeChange={setMfaCode}
                    onRecoveryCodeChange={setMfaRecoveryCode}
                    onReset={() => {
                      setMfaChallenge(null)
                      setMfaCode('')
                      setMfaRecoveryCode('')
                    }}
                    onSubmit={handleMfaVerify}
                    recoveryCode={mfaRecoveryCode}
                  />
                ) : (
                  <AuthForm
                    buttonLabel="Sign In"
                    fields={signInFields}
                    isSubmitting={isSubmitting}
                    onFieldChange={handleSignInChange}
                    onSubmit={(event) => handleSubmit('signin', event)}
                    title="Sign in"
                    values={signInValues}
                  >
                    <button className="codepen-auth__link" type="button">
                      Forgot your password?
                    </button>
                  </AuthForm>
                )}
              </div>

              <div className="codepen-auth__overlay-container" aria-hidden="true">
                <div className="codepen-auth__overlay">
                  <div className="codepen-auth__overlay-panel codepen-auth__overlay-left">
                    <h1>Already have an account?</h1>
                    <p>Sign in to open your workspace.</p>
                    <button
                      className="codepen-auth__ghost-button"
                      onClick={() => setIsSignUpActive(false)}
                      type="button"
                    >
                      Sign In
                    </button>
                  </div>

                  <div className="codepen-auth__overlay-panel codepen-auth__overlay-right">
                    <h1>New to NeuroMarketer?</h1>
                    <p>Create an account and start scoring creative in minutes.</p>
                    <button
                      className="codepen-auth__ghost-button"
                      onClick={() => setIsSignUpActive(true)}
                      type="button"
                    >
                      Sign Up
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </main>
  )
}

type AuthFormProps = {
  title: string
  buttonLabel: string
  fields: AuthField[]
  values: Record<string, string>
  onFieldChange: (fieldName: string, value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  isSubmitting: boolean
  children?: ReactNode
}

function AuthForm({
  title,
  buttonLabel,
  fields,
  values,
  onFieldChange,
  onSubmit,
  isSubmitting,
  children,
}: AuthFormProps) {
  return (
    <form className="codepen-auth__form" onSubmit={onSubmit}>
      <h1>{title}</h1>

      <div className="codepen-auth__fields">
        {fields.map((field) => (
          <input
            aria-label={field.label}
            autoComplete={field.autoComplete}
            className="codepen-auth__input"
            id={field.id}
            key={field.id}
            name={field.name}
            onChange={(event) => onFieldChange(field.name, event.target.value)}
            placeholder={field.placeholder}
            required
            type={field.type}
            value={values[field.name] ?? ''}
          />
        ))}
      </div>

      {children}

      <button className="codepen-auth__submit" disabled={isSubmitting} type="submit">
        {isSubmitting ? 'Please wait...' : buttonLabel}
      </button>
    </form>
  )
}

type InviteAcceptFormProps = {
  invitePreview: InvitePreview
  values: SignUpValues
  isSubmitting: boolean
  onFieldChange: (fieldName: string, value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

function InviteAcceptForm({
  invitePreview,
  values,
  isSubmitting,
  onFieldChange,
  onSubmit,
}: InviteAcceptFormProps) {
  return (
    <form className="codepen-auth__form" onSubmit={onSubmit}>
      <h1>Accept Invite</h1>
      <p>
        Join {invitePreview.workspace_name} as {invitePreview.role}.
      </p>

      <div className="codepen-auth__fields">
        <input
          aria-label="Full name"
          autoComplete="name"
          className="codepen-auth__input"
          onChange={(event) => onFieldChange('fullName', event.target.value)}
          placeholder="Name"
          required
          type="text"
          value={values.fullName}
        />
        <input
          aria-label="Email address"
          autoComplete="email"
          className="codepen-auth__input"
          readOnly
          type="email"
          value={invitePreview.email}
        />
        <input
          aria-label="Password"
          autoComplete="new-password"
          className="codepen-auth__input"
          onChange={(event) => onFieldChange('password', event.target.value)}
          placeholder="Password"
          required
          type="password"
          value={values.password}
        />
      </div>

      <button className="codepen-auth__submit" disabled={isSubmitting} type="submit">
        {isSubmitting ? 'Please wait...' : 'Accept invite'}
      </button>
    </form>
  )
}

type MfaChallengeFormProps = {
  email: string
  code: string
  recoveryCode: string
  isSubmitting: boolean
  onCodeChange: (value: string) => void
  onRecoveryCodeChange: (value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onReset: () => void
}

function MfaChallengeForm({
  email,
  code,
  recoveryCode,
  isSubmitting,
  onCodeChange,
  onRecoveryCodeChange,
  onSubmit,
  onReset,
}: MfaChallengeFormProps) {
  return (
    <form className="codepen-auth__form" onSubmit={onSubmit}>
      <h1>Verify MFA</h1>
      <p>Enter the authenticator code for {email} or use a recovery code.</p>

      <div className="codepen-auth__fields">
        <input
          aria-label="Authenticator code"
          autoComplete="one-time-code"
          className="codepen-auth__input"
          onChange={(event) => onCodeChange(event.target.value)}
          placeholder="6-digit code"
          type="text"
          value={code}
        />
        <input
          aria-label="Recovery code"
          className="codepen-auth__input"
          onChange={(event) => onRecoveryCodeChange(event.target.value)}
          placeholder="Recovery code"
          type="text"
          value={recoveryCode}
        />
      </div>

      <button className="codepen-auth__link" onClick={onReset} type="button">
        Use another account
      </button>

      <button className="codepen-auth__submit" disabled={isSubmitting} type="submit">
        {isSubmitting ? 'Please wait...' : 'Verify and continue'}
      </button>
    </form>
  )
}

export default HomePage
