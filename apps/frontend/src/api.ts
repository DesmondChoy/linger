const BASE_URL = import.meta.env.VITE_API_URL ?? ''

export async function sendMessage(sessionId: string, message: string): Promise<string> {
  const response = await fetch(`${BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })

  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `Request failed (${response.status})`)
  }

  const data: { reply: string } = await response.json()
  return data.reply
}

export async function resetSession(sessionId: string): Promise<void> {
  await fetch(`${BASE_URL}/api/sessions/${sessionId}`, { method: 'DELETE' })
}
