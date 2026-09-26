import { setAccessToken } from './api'

export type Account = { username: string, token: string }

const STORAGE_KEY = 'linger.account'

/** The account remembered by this browser, if any. */
export function restoreAccount(): Account | null {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null') as Account | null
    setAccessToken(stored?.token)
    return stored
  } catch {
    return null
  }
}

export function rememberAccount(account: Account | null) {
  setAccessToken(account?.token)
  try {
    if (account) localStorage.setItem(STORAGE_KEY, JSON.stringify(account))
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Storage can be unavailable (private mode); sign-in still lasts for this page.
  }
}
