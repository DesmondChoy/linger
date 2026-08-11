import { useState } from 'react'
import { resetSession, sendMessage } from '../api'
import type { Message } from '../types'
import { Composer } from './Composer'
import { MemoryDrawer } from './MemoryDrawer'
import { MessageList } from './MessageList'

export function Chat() {
  // One session per page load. Reloading starts a fresh conversation.
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const [messages, setMessages] = useState<Message[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [memoryOpen, setMemoryOpen] = useState(false)

  async function handleSend(text: string) {
    setMessages((current) => [
      ...current,
      { role: 'user', content: text },
      { role: 'assistant', content: '' },
    ])
    setPending(true)
    setError(null)

    try {
      const reply = await sendMessage(sessionId, text)
      setMessages((current) => [
        ...current.slice(0, -1),
        { role: 'assistant', content: reply },
      ])
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
    setError(null)
  }

  return (
    <main className={`workspace${memoryOpen ? ' drawer-open' : ''}`}>
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
            <button
              className="quiet-button memory-button"
              type="button"
              onClick={() => setMemoryOpen((open) => !open)}
              aria-expanded={memoryOpen}
            >
              Memories
            </button>
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

        <MessageList messages={messages} pending={pending} />

        {error && <p className="error">{error}</p>}

        <Composer disabled={pending} onSend={handleSend} />
      </section>

      {memoryOpen && <MemoryDrawer onClose={() => setMemoryOpen(false)} />}
    </main>
  )
}
