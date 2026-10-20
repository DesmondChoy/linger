import { useEffect, useState } from 'react'
import { rememberAccount, restoreAccount, type Account } from './account'
import { setUnauthorizedHandler, signOut } from './api'
import { Chat } from './components/Chat'
import { Landing } from './components/Landing'
import { Scenarios } from './replay/Scenarios'

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
        onOpenScenarios={() => setView('synthetic')}
      />
    )
  }
  if (view === 'synthetic') {
    return <Scenarios onHome={() => setView('landing')} signedIn={account !== null} onOpenLive={() => setView('live')} />
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
