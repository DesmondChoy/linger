import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatRequestError, resetSession, sendMessage } from './api'

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
  it('sends one Muse message and retains server trace correlation', async () => {
    const payload = {
      reply: 'A reflection',
      inspection: {
        muse_turn: {
          turn_id: 'turn-1',
          user_message: 'What stayed with me?',
          reading_context: null,
          policy: {
            spoiler_ceiling: null,
            allow_retrieval: false,
            allow_connection: false,
            allow_memory_capture: false,
          },
        },
        context_resolution: {
          status: 'unknown',
          work_id: null,
          work_title: null,
          chapter_max: null,
          boundary_source: null,
          explanation: 'No book context.',
        },
        traces: [],
        connection_decline: null,
        librarian_grounding: [],
        prompt: '{}',
        release: null,
      },
      trace: {
        trace_id: '01979d1e4e4325335569dba4459473fc',
      },
      memory_capture: null,
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload))
    vi.stubGlobal('fetch', fetchMock)

    await expect(sendMessage('session-1', 'What stayed with me?', 'turn-1')).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chat',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          session_id: 'session-1',
          turn_id: 'turn-1',
          message: 'What stayed with me?',
        }),
      }),
    )
  })

  it('retains safe trace correlation when a request fails', async () => {
    const trace = {
      trace_id: '01979d1e4e4325335569dba4459473fc',
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      detail: { message: 'The model call failed. Try again.', trace },
    }, 502)))

    await expect(
      sendMessage('session-1', 'Hello', 'turn-1'),
    ).rejects.toMatchObject({
      name: 'ChatRequestError',
      message: 'The model call failed. Try again.',
      trace,
    } satisfies Partial<ChatRequestError>)
  })
})

describe('session API', () => {
  it('resets only the selected conversation', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await resetSession('session / 1')

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session%20%2F%201', { method: 'DELETE' })
  })
})
