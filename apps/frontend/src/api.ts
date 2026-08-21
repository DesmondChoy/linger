import type { ChatResult } from './types'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

export async function sendMessage(
  sessionId: string,
  message: string,
): Promise<ChatResult> {
  const response = await fetch(`${BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })

  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `Request failed (${response.status})`)
  }

  const payload: unknown = await response.json()
  if (typeof payload !== 'object' || payload === null || !('reply' in payload) || typeof payload.reply !== 'string' || !('inspection' in payload)) {
    throw new Error('The server returned an invalid response.')
  }
  return payload as ChatResult
}

export async function resetSession(sessionId: string): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/sessions/${sessionId}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
}
