import { test as base, expect, type Request } from '@playwright/test'
import type { ChatResult } from '../src/types.ts'

export const reply = 'What stayed with you about that moment?'

const result = {
  reply,
  sources: [],
  trace: { trace_id: '0123456789abcdef0123456789abcdef' },
  memory_capture: null,
  inspection: {
    muse_turn: {
      turn_id: 'browser-test-turn', user_message: 'A reflection', reading_context: null,
      policy: {
        spoiler_ceiling: null, allow_retrieval: false, allow_connection: false, allow_memory_capture: false,
        emotional_content: {
          version: '3', boundary_response_id: 'distressing_disclosure_v1', self_harm_response_id: 'self_harm_disclosure_v1',
          prohibit_diagnosis: true, stop_probing_after_distress: true, suppress_tools_after_distress: true, suppress_capture_after_distress: true,
        },
      },
    },
    context_resolution: {
      status: 'unknown', work_id: null, work_title: null, book_version_id: null, chapter_max: null,
      part_id: 'main', unit_ids: [], boundary_source: null, boundary_authorization_basis: null,
      boundary_confidence: null, boundary_supporting_memory_ids: [], boundary_supporting_locations: [],
      clarification_question: null, explanation: 'No book is needed for this reflection.',
    },
    traces: [], connection_decline: null, librarian_grounding: [], prompt: '', release: null,
  },
} satisfies ChatResult

export const test = base.extend<{ apiRequests: Request[] }>({
  apiRequests: [async ({ page }, use) => {
    const requests: Request[] = []
    const unexpected: string[] = []
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route('**/api/**', async (route) => {
      const request = route.request()
      requests.push(request)
      const path = new URL(request.url()).pathname
      if (path === '/api/auth/login' && request.method() === 'POST') {
        await route.fulfill({ json: { username: 'browser-reader', token: 'browser-test-token' } })
      } else if (path === '/api/history' && request.method() === 'GET') {
        await route.fulfill({ json: [] })
      } else if (path === '/api/chat/stream' && request.method() === 'POST') {
        const payload: unknown = request.postDataJSON()
        if (typeof payload !== 'object' || payload === null
          || !('message' in payload) || typeof payload.message !== 'string'
          || !('turn_id' in payload) || typeof payload.turn_id !== 'string') {
          unexpected.push('Invalid chat request')
          await route.abort()
          return
        }
        const response: ChatResult = {
          ...result,
          inspection: {
            ...result.inspection,
            muse_turn: { ...result.inspection.muse_turn, turn_id: payload.turn_id, user_message: payload.message },
          },
        }
        await route.fulfill({ contentType: 'text/event-stream', body: `event: result\ndata: ${JSON.stringify(response)}\n\n` })
      } else {
        unexpected.push(`${request.method()} ${path}`)
        await route.abort()
      }
    })
    await use(requests)
    expect(unexpected, 'Unexpected API calls').toEqual([])
    expect(errors, 'Uncaught browser errors').toEqual([])
  }, { auto: true }],
})

export { expect } from '@playwright/test'
