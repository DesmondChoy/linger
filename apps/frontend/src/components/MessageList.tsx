import { useEffect, useRef } from 'react'
import type { Message } from '../types'

type Props = {
  messages: Message[]
  pending: boolean
}

export function MessageList({ messages, pending }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pending])

  return (
    <div className="messages">
      {messages.length === 0 && !pending && (
        <p className="empty">Start the conversation below.</p>
      )}

      {messages.map((message, index) => (
        <div key={index} className={`bubble ${message.role}`}>
          {message.content}
        </div>
      ))}

      {pending && <div className="bubble assistant thinking">Thinking…</div>}

      <div ref={bottomRef} />
    </div>
  )
}
