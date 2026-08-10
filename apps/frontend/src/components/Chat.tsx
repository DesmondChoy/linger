import { useState } from 'react'
import { resetSession, sendMessage } from '../api'
import type { Message } from '../types'
import { Composer } from './Composer'
import { MessageList } from './MessageList'

export function Chat() {
  // One session per page load. Reloading starts a fresh conversation.
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const [messages, setMessages] = useState<Message[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
    <div className="chat">
      <header>
        <h1>Linger</h1>
        <button type="button" onClick={handleReset} disabled={pending || !messages.length}>
          New chat
        </button>
      </header>

      <MessageList messages={messages} pending={pending} />

      {error && <p className="error">{error}</p>}

      <Composer disabled={pending} onSend={handleSend} />
    </div>
  )
}
