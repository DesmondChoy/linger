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
    // The empty assistant bubble is added up front so every delta is simply an
    // append to the last message — no flag tracking whether it exists yet.
    setMessages((current) => [
      ...current,
      { role: 'user', content: text },
      { role: 'assistant', content: '' },
    ])
    setPending(true)
    setError(null)

    try {
      await sendMessage(sessionId, text, (delta) => {
        setMessages((current) => {
          const last = current[current.length - 1]
          return [...current.slice(0, -1), { ...last, content: last.content + delta }]
        })
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Something went wrong.')
      // Drop the placeholder so a failed turn leaves no empty bubble behind.
      setMessages((current) =>
        current[current.length - 1]?.content === '' ? current.slice(0, -1) : current,
      )
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
