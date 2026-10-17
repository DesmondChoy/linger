import { useMemo, useState } from 'react'
import { Architecture } from '../components/architecture/Architecture'
import { MessageList } from '../components/MessageList'
import { replayRun } from './adapter'
import type { Persona } from './types'

type Props = {
  persona: Persona
  onBack: () => void
  onHome: () => void
}

function runLabel(startedAt: string | null, index: number): string {
  if (!startedAt) return `Run ${index + 1}`
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(startedAt))
}

/**
 * One persona's recorded run in the same chat, map and Inspect surfaces as a
 * live conversation. Nothing here can send a message or change an account.
 */
export function PersonaReplay({ persona, onBack, onHome }: Props) {
  const [runIndex, setRunIndex] = useState(0)
  const run = persona.runs[runIndex] ?? persona.runs[0]
  const { messages, timeline } = useMemo(() => replayRun(persona, run), [persona, run])

  return (
    <main className="workspace replay-workspace">
      <section className="chat" aria-label="Recorded conversation">
        <header className="chat-header">
          <button type="button" className="brand brand-home" onClick={onHome} aria-label="Linger — back to the start page">
            <span aria-hidden="true">L</span>
            <span className="brand-text">
              <span className="brand-name">Linger</span>
              <span className="brand-tagline">Recorded evaluation · read-only</span>
            </span>
          </button>
          <div className="header-actions">
            {persona.runs.length > 1 && (
              <label className="replay-run-picker">
                Run
                <select value={runIndex} onChange={(event) => setRunIndex(Number(event.target.value))}>
                  {persona.runs.map((item, index) => (
                    <option key={item.id} value={index}>{runLabel(item.startedAt, index)} · {item.passed}/{item.total}</option>
                  ))}
                </select>
              </label>
            )}
            <button type="button" className="quiet-button" onClick={onBack}>All personas</button>
          </div>
        </header>

        <section className="persona-brief">
          <p className="eyebrow">{persona.dated} · {run.model ?? 'model not recorded'}</p>
          <h2>{persona.title}</h2>
          <p>{persona.description}</p>
          <p className="persona-result">
            <b>{run.passed}/{run.total} scenes passed</b>
            {run.ungraded > 0 && <> · {run.ungraded} ungraded</>}
            {run.executionFailures > 0 && <> · {run.executionFailures} execution {run.executionFailures === 1 ? 'fault' : 'faults'}</>}
            {run.logfireUrl && <> · <a href={run.logfireUrl} target="_blank" rel="noreferrer">Logfire</a></>}
          </p>
          {run.verdict && <p className="persona-verdict"><span className="eyebrow">Reviewer's verdict</span>{run.verdict}</p>}
          <details>
            <summary>Who this persona is</summary>
            <p className="persona-context">{persona.context}</p>
          </details>
          {persona.props.length > 0 && (
            <details>
              <summary>Placed in the account before the run ({persona.props.length})</summary>
              <ul className="persona-props">
                {persona.props.map((prop) => <li key={prop.id}>{prop.text}</li>)}
              </ul>
            </details>
          )}
        </section>

        <MessageList messages={messages} pending={false} />
        <p className="replay-bar">Recorded run · read-only. Replies are exactly what this build said; nothing is sent.</p>
      </section>

      <section className="analysis" aria-label="How this works">
        <Architecture key={run.id} timeline={timeline} progress={[]} pendingMessage={null} />
      </section>
    </main>
  )
}
