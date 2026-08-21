import { afterEach, describe, expect, it, vi } from 'vitest'
import { resetSession, sendMessage } from './api'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('chat API', () => {
  it('sends one Muse message with server-owned session context', async () => {
    const payload = { reply: 'A reflection', inspection: {}, memory_capture: null }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload))
    vi.stubGlobal('fetch', fetchMock)

    await expect(sendMessage('session-1', 'What stayed with me?')).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chat',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          session_id: 'session-1',
          message: 'What stayed with me?',
        }),
      }),
    )
  })

  it('resets only the selected conversation', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await resetSession('session-1')

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1', {
      method: 'DELETE',
    })
  })
})
