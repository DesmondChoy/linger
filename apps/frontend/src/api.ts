import type {
  ChatResult,
  ProgressEvent,
  Conversation,
  TraceReference,
} from './types'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

let accessToken: string | undefined
let onUnauthorized: () => void = () => {}

/** Set by the sign-in layer; account-scoped requests carry it as a bearer token. */
export function setAccessToken(token: string | undefined) {
  accessToken = token
}

/** Called when the server no longer accepts the token, so the app can sign out. */
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

async function accountFetch(
  url: string,
  init: Omit<RequestInit, 'headers'> & { headers?: Record<string, string> } = {},
): Promise<Response> {
  const response = await fetch(url, { ...init, headers: { ...init.headers, ...authHeaders() } })
  if (response.status === 401) onUnauthorized()
  return response
}

export type SignedIn = { username: string, token: string }

export class SignInError extends Error {}

/** Create an account (`signup`) or sign in to an existing one (`login`). */
export async function signIn(
  mode: 'login' | 'signup',
  username: string,
  password: string,
): Promise<SignedIn> {
  const response = await fetch(`${BASE_URL}/api/auth/${mode}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = isRecord(payload) ? payload.detail : undefined
    throw new SignInError(
      typeof detail === 'string'
        ? detail
        : response.status === 422
          ? 'Usernames need 3–32 letters, numbers, dots, dashes or underscores; passwords at least 6 characters.'
          : `Sign-in failed (${response.status})`,
    )
  }
  return payload as SignedIn
}

export async function signOut(): Promise<void> {
  await fetch(`${BASE_URL}/api/auth/logout`, { method: 'POST', headers: authHeaders() }).catch(() => {})
}

function authHeaders(): Record<string, string> {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {}
}

export class ChatRequestError extends Error {
  readonly trace?: TraceReference

  constructor(message: string, trace?: TraceReference) {
    super(message)
    this.name = 'ChatRequestError'
    this.trace = trace
  }
}

const PROGRESS_STATUSES = ['running', 'complete', 'declined', 'failed']

/**
 * Run one turn over the progress stream.
 *
 * The server emits content-free `progress` frames while the agents work, then
 * exactly one `result` or `error` frame carrying the same atomic contract the
 * non-streaming endpoint returns.
 */
export async function sendMessage(
  sessionId: string,
  message: string,
  turnId: string,
  onProgress: (event: ProgressEvent) => void,
): Promise<ChatResult> {
  const response = await accountFetch(`${BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, turn_id: turnId, message }),
  })

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    const detail = isRecord(payload) ? payload.detail : undefined
    throw new ChatRequestError(
      isRecord(detail) && typeof detail.message === 'string'
        ? detail.message
        : typeof detail === 'string'
          ? detail
          : `Request failed (${response.status})`,
      isRecord(detail) && isTraceReference(detail.trace) ? detail.trace : undefined,
    )
  }
  if (!response.body) {
    throw new ChatRequestError('The server did not provide a progress stream.')
  }

  let result: ChatResult | null = null
  let failure: ChatRequestError | null = null

  function consumeFrame(frame: string) {
    if (!frame.trim() || frame.trimStart().startsWith(':')) return
    let eventName = 'message'
    const data: string[] = []
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
    }
    if (!data.length) return

    let payload: unknown
    try {
      payload = JSON.parse(data.join('\n'))
    } catch {
      throw new ChatRequestError('The server returned an invalid progress event.')
    }

    if (eventName === 'progress') {
      if (!isProgressEvent(payload)) {
        throw new ChatRequestError('The server returned invalid progress metadata.')
      }
      onProgress(payload)
    } else if (eventName === 'result') {
      result = payload as ChatResult
    } else if (eventName === 'error') {
      const detail = isRecord(payload) ? payload : {}
      failure = new ChatRequestError(
        typeof detail.detail === 'string' ? detail.detail : 'The request failed.',
        isTraceReference(detail.trace) ? detail.trace : undefined,
      )
    }
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const frames = buffer.split(/\r?\n\r?\n/)
    buffer = frames.pop() ?? ''
    for (const frame of frames) consumeFrame(frame)
    if (done) break
  }
  if (buffer.trim()) consumeFrame(buffer)

  if (failure) throw failure
  if (!result) {
    throw new ChatRequestError('The progress stream ended before a reply arrived.')
  }
  return result
}

function isProgressEvent(value: unknown): value is ProgressEvent {
  return isRecord(value)
    && typeof value.sequence === 'number'
    && typeof value.elapsed_ms === 'number'
    && typeof value.agent === 'string'
    && typeof value.stage === 'string'
    && typeof value.detail === 'string'
    && typeof value.input_origin === 'string'
    && typeof value.output_receiver === 'string'
    && PROGRESS_STATUSES.includes(String(value.status))
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isTraceReference(value: unknown): value is TraceReference {
  return isRecord(value)
    && /^[0-9a-f]{32}$/.test(String(value.trace_id))
}

function sessionUrl(sessionId: string): string {
  return `${BASE_URL}/api/sessions/${encodeURIComponent(sessionId)}`
}

/** Every saved conversation of the signed-in reader, oldest first. */
export async function loadHistory(): Promise<Conversation[]> {
  const response = await accountFetch(`${BASE_URL}/api/history`)
  if (!response.ok) throw new Error(`Could not load earlier chats (${response.status})`)
  return response.json() as Promise<Conversation[]>
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await accountFetch(sessionUrl(sessionId), { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Delete failed (${response.status})`)
  }
}
