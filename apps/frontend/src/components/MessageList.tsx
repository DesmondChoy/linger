import { useEffect, useRef } from 'react'
import type { Message } from '../types'

type Props = { messages: Message[]; pending: boolean }

export function MessageList({ messages, pending }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pending])

  return (
    <div className="messages">
      {messages.length === 0 && !pending && <p className="empty">Start the conversation below.</p>}

      {messages.map((message, index) =>
        message.role === 'assistant' && message.content === '' ? (
          <div key={index} className="bubble assistant thinking">Thinking…</div>
        ) : (
          <div key={message.id} className={`bubble ${message.role}`}>
            <div>{message.content}</div>
          </div>
        ),
      )}

      <div ref={bottomRef} />
    </div>
  )
}
