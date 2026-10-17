import { useEffect, useState } from 'react'
import { rememberAccount, restoreAccount, type Account } from './account'
import { setUnauthorizedHandler, signOut } from './api'
import { Chat } from './components/Chat'
import { Landing } from './components/Landing'
import { Personas } from './replay/Personas'

type View = 'landing' | 'live' | 'synthetic'

export default function App() {
  const [account, setAccount] = useState<Account | null>(restoreAccount)
  const [view, setView] = useState<View>('landing')

  function forgetAccount() {
    rememberAccount(null)
    setAccount(null)
    setView('landing')
  }

  useEffect(() => setUnauthorizedHandler(forgetAccount), [])

  async function handleSignOut() {
    await signOut()
    forgetAccount()
  }

  if (view === 'live' && account) {
    return (
      <Chat
        username={account.username}
        onHome={() => setView('landing')}
        onSignOut={handleSignOut}
        onOpenPersonas={() => setView('synthetic')}
      />
    )
  }
  if (view === 'synthetic') {
    return <Personas onHome={() => setView('landing')} />
  }
  return (
    <Landing
      account={account}
      onSignedIn={(signedIn) => {
        rememberAccount(signedIn)
        setAccount(signedIn)
        setView('live')
      }}
      onContinue={() => setView('live')}
      onSignOut={handleSignOut}
      onOpenSynthetic={() => setView('synthetic')}
    />
  )
}
