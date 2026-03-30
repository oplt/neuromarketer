import { useState, type FormEvent, type ReactNode } from 'react'
import type { AuthSession } from '../lib/session'
import './home-page.css'

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
  type: 'success' | 'error'
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

const proofPoints = [
  { value: '5', label: 'Decision scores before launch' },
  { value: '1 feed', label: 'Creative review system for teams' },
  { value: '<24h', label: 'From upload to recommendation loop' },
]

const workflow = [
  'Upload a video, image, audio, or text asset',
  'Promote winning artifacts into creative versions',
  'Generate attention, emotion, memory, load, and conversion-proxy outputs',
  'Move straight into compare and optimize without another tool handoff',
]

const dashboardNotes = [
  'Current account health, launch status, and job queue in one view',
  'Simple left navigation focused on Home, Account, and Profile',
  'Built to feel closer to a clean Mantis-style admin shell than a marketing splash page',
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
      const endpoint = mode === 'signup' ? '/api/v1/auth/signup' : '/api/v1/auth/signin'
      const payload =
        mode === 'signup'
          ? {
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

      if (mode === 'signup') {
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
            <span className="landing-page__eyebrow">Neuromarketing SaaS for pre-launch decisions</span>
            <h1>Predict what creative will do before spend starts moving.</h1>
            <p>
              Wrap multimodal brain-response modeling behind a product teams can actually use:
              upload assets, score attention and memory, compare versions, and turn outputs into
              creative direction your marketing org can ship on.
            </p>
          </div>

          <div className="landing-page__proof-grid" aria-label="Product proof points">
            {proofPoints.map((item) => (
              <article className="proof-card" key={item.label}>
                <strong>{item.value}</strong>
                <span>{item.label}</span>
              </article>
            ))}
          </div>

          <section className="signal-board">
            <div className="signal-board__header">
              <span className="signal-board__eyebrow">Platform arc</span>
              <h2>One system from upload to recommendation.</h2>
            </div>

            <div className="signal-board__grid">
              <article className="signal-card signal-card--lead">
                <span className="signal-card__label">Core workflow</span>
                <ol className="signal-list signal-list--ordered">
                  {workflow.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ol>
              </article>

              <article className="signal-card">
                <span className="signal-card__label">Dashboard direction</span>
                <ul className="signal-list">
                  {dashboardNotes.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </article>
            </div>
          </section>
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
                <AuthForm
                  buttonLabel="Sign Up"
                  fields={signUpFields}
                  isSubmitting={isSubmitting}
                  onFieldChange={handleSignUpChange}
                  onSubmit={(event) => handleSubmit('signup', event)}
                  title="Create Account"
                  values={signUpValues}
                />
              </div>

              <div className="codepen-auth__form-container codepen-auth__sign-in-container">
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
              </div>

              <div className="codepen-auth__overlay-container" aria-hidden="true">
                <div className="codepen-auth__overlay">
                  <div className="codepen-auth__overlay-panel codepen-auth__overlay-left">
                    <h1>Already have an account?</h1>
                    <p>Login to access your dashboard and experience the power of the web.</p>
                    <button
                      className="codepen-auth__ghost-button"
                      onClick={() => setIsSignUpActive(false)}
                      type="button"
                    >
                      Sign In
                    </button>
                  </div>

                  <div className="codepen-auth__overlay-panel codepen-auth__overlay-right">
                    <h1>Don&apos;t have an account?</h1>
                    <p>Create an account and let&apos;s begin a new journey.</p>
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

export default HomePage
