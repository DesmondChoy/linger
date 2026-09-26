import { useState, type FormEvent } from 'react'
import { signIn } from '../api'
import type { Account } from '../account'
import { landing } from '../landing/content'

type Props = {
  account: Account | null
  onSignedIn: (account: Account) => void
  onContinue: () => void
  onSignOut: () => void
  onOpenSynthetic: () => void
}

export function Landing({ account, onSignedIn, onContinue, onSignOut, onOpenSynthetic }: Props) {
  return (
    <main className="landing">
      <header className="landing-hero">
        <div className="brand">
          <span aria-hidden="true">{landing.brandMark}</span>
          <div>
            <h1>{landing.title}</h1>
            <p>{landing.tagline}</p>
          </div>
        </div>
        <p className="landing-intro">{landing.intro}</p>
      </header>

      <div className="landing-paths">
        {landing.live.enabled && (
          <section className="landing-card" aria-labelledby="landing-live">
            <h2 id="landing-live">{landing.live.heading}</h2>
            <p>{landing.live.body}</p>
            {account ? (
              <div className="landing-actions">
                <button type="button" onClick={onContinue}>{landing.live.continueLabel(account.username)}</button>
                <button type="button" className="quiet-button" onClick={onSignOut}>
                  {landing.live.signOutLabel}
                </button>
              </div>
            ) : (
              <SignInForm onSignedIn={onSignedIn} />
            )}
          </section>
        )}

        {landing.synthetic.enabled && (
          <section className="landing-card" aria-labelledby="landing-synthetic">
            <h2 id="landing-synthetic">{landing.synthetic.heading}</h2>
            <p>{landing.synthetic.body}</p>
            <div className="landing-actions">
              <button type="button" onClick={onOpenSynthetic}>{landing.synthetic.openLabel}</button>
            </div>
          </section>
        )}
      </div>

      <footer className="landing-footer">{landing.footer}</footer>
    </main>
  )
}

function SignInForm({ onSignedIn }: { onSignedIn: (account: Account) => void }) {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSignedIn(await signIn(mode, username.trim(), password))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="sign-in-form" onSubmit={handleSubmit}>
      <label>
        Username
        <input
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
          required
        />
      </label>
      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          required
        />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="landing-actions">
        <button type="submit" disabled={busy}>
          {mode === 'login' ? landing.live.signInLabel : landing.live.signUpLabel}
        </button>
        <button
          type="button"
          className="link-button"
          onClick={() => {
            setMode(mode === 'login' ? 'signup' : 'login')
            setError(null)
          }}
        >
          {mode === 'login' ? landing.live.switchToSignUp : landing.live.switchToSignIn}
        </button>
      </div>
    </form>
  )
}
