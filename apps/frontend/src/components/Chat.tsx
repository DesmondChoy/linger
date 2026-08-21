import { useState } from 'react'
import { resetSession, sendMessage } from '../api'
import type { MemoryCaptureNotice, Message, TurnInspection, TurnTimeline } from '../types'
import { Composer } from './Composer'
import { MessageList } from './MessageList'
import { Inspector } from './Inspector'
import { Reader } from './Reader'

export function Chat() {
  // One session per page load. Reloading starts a fresh conversation.
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const [messages, setMessages] = useState<Message[]>([])
  const [timeline, setTimeline] = useState<TurnTimeline[]>([])
  const [view, setView] = useState<'chat' | 'inspect'>('chat')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [captureNotice, setCaptureNotice] = useState<MemoryCaptureNotice | null>(null)

  async function handleSend(text: string) {
    const turnId = crypto.randomUUID()
    setMessages((current) => [
      ...current,
      { id: turnId, role: 'user', content: text },
      { id: `${turnId}-assistant`, role: 'assistant', content: '' },
    ])
    setPending(true)
    setError(null)

    try {
      const result = await sendMessage(sessionId, text)
      setMessages((current) => [
        ...current.slice(0, -1),
        { ...current[current.length - 1], content: result.reply },
      ])
      setTimeline((current) => [...current, timelineFromInspection(result.inspection, text, result.reply, turnId)])
      setCaptureNotice(result.memory_capture)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Something went wrong.')
      // The server stores nothing on a failed request, so roll back both local
      // messages and keep the two histories aligned.
      setMessages((current) => current.slice(0, -2))
    } finally {
      setPending(false)
    }
  }

  async function handleReset() {
    await resetSession(sessionId)
    setSessionId(crypto.randomUUID())
    setMessages([])
    setTimeline([])
    setError(null)
    setCaptureNotice(null)
  }

  return (
    <main className="workspace">
      <Reader disabled={pending} />
      <section className="chat" aria-label="Reflection chat">
        <header className="chat-header">
          <div className="brand">
            <span aria-hidden="true">L</span>
            <div>
              <h1>Linger</h1>
              <p>Notice what stays with you.</p>
            </div>
          </div>
          <div className="header-actions">
            <div className="view-tabs" role="tablist" aria-label="Chat views">
              <button type="button" role="tab" aria-selected={view === 'chat'} onClick={() => setView('chat')}>Chat</button>
              <button type="button" role="tab" aria-selected={view === 'inspect'} onClick={() => setView('inspect')}>Inspect</button>
            </div>
            <button
              className="quiet-button"
              type="button"
              onClick={handleReset}
              disabled={pending || !messages.length}
            >
              New chat
            </button>
          </div>
        </header>

        {view === 'chat' ? <>
          <MessageList messages={messages} pending={pending} />
          {captureNotice && (
            <p className="notice">
              <span>{captureNotice.notice}</span>
            </p>
          )}
          {error && <p className="error">{error}</p>}
          <Composer disabled={pending} onSend={handleSend} />
        </> : <Inspector timeline={timeline} />}
      </section>
    </main>
  )
}

function timelineFromInspection(inspection: TurnInspection, userInput: string, response: string, fallbackId: string): TurnTimeline {
  return {
    id: inspection.muse_turn.turn_id ?? fallbackId,
    userInput,
    response,
    traces: inspection.traces,
    contract: inspection.muse_turn,
    contextResolution: inspection.context_resolution,
    promptInspection: { dynamic_input: inspection.prompt },
    connectionBrief: inspection.connection_brief ?? undefined,
    librarianRequest: inspection.librarian_request ?? undefined,
    evidenceBundle: inspection.evidence_bundle ?? undefined,
    connection: inspection.connection_proposal ?? undefined,
    release: inspection.release ?? undefined,
    status: inspection.release?.release_source === 'application_safe_decline' ? 'failed' : 'complete',
  }
}
