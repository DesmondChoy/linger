const BASE_URL = import.meta.env.VITE_API_URL ?? ''

/**
 * Stream a reply, invoking `onDelta` with each chunk as it arrives.
 *
 * The backend commits a 200 before the model runs, so a mid-stream failure
 * arrives as an SSE `error` event rather than a bad status; both paths throw.
 */
export async function sendMessage(
  sessionId: string,
  message: string,
  onDelta: (delta: string) => void,
): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })

  if (!response.ok || !response.body) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `Request failed (${response.status})`)
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    // Events are separated by a blank line; a chunk can split one in half.
    buffer += value
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''

    for (const block of blocks) {
      const name = block.match(/^event: (.*)$/m)?.[1]
      const raw = block.match(/^data: (.*)$/m)?.[1]
      if (!name || raw === undefined) continue

      const payload: string = JSON.parse(raw)
      if (name === 'error') throw new Error(payload)
      if (name === 'delta') onDelta(payload)
    }
  }
}

export async function resetSession(sessionId: string): Promise<void> {
  await fetch(`${BASE_URL}/api/sessions/${sessionId}`, { method: 'DELETE' })
}
