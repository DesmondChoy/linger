import { useMemo, useState } from 'react'
import { loadScenarioProps } from '../api'
import { Architecture } from '../components/architecture/Architecture'
import { MessageList } from '../components/MessageList'
import { replayRun } from './adapter'
import type { Scenario } from './types'

type Props = {
  scenario: Scenario
  onBack: () => void
  onHome: () => void
  /** Whether a reader is signed in, so the scenario's Props can be loaded into their account. */
  signedIn: boolean
  onOpenLive: () => void
}

const RECORDED_MEMORY_NOTE =
  'Recorded run: the Props placed in the account before it, memories it saved, and what its curation Scenes applied. ' +
  'Each curation Scene ran on its own copy of the Props, so nothing here is retired.'

/** Copies the scenario's Props into the reader's own account, so a live chat starts from the same memories. */
function LoadProps({ scenario, signedIn, onOpenLive }: { scenario: Scenario; signedIn: boolean; onOpenLive: () => void }) {
  const [state, setState] = useState<{ status: 'idle' | 'loading' } | { status: 'done'; text: string } | { status: 'error'; text: string }>({ status: 'idle' })
  if (!signedIn) {
    return <p className="muted">Sign in to load these memories into your own account and chat from the same starting point.</p>
  }
  async function load() {
    setState({ status: 'loading' })
    try {
      const { loaded, already_saved: already } = await loadScenarioProps(scenario.id)
      setState({ status: 'done', text: `Saved ${loaded} ${loaded === 1 ? 'memory' : 'memories'} to your account${already ? `; ${already} were already there` : ''}.` })
    } catch (reason) {
      setState({ status: 'error', text: reason instanceof Error ? reason.message : String(reason) })
    }
  }
  return (
    <div className="scenario-load">
      {state.status === 'done' ? (
        <p>
          {state.text}{' '}
          <button type="button" className="quiet-button" onClick={onOpenLive}>Open live chat</button>
        </p>
      ) : (
        <button type="button" className="quiet-button" disabled={state.status === 'loading'} onClick={() => void load()}>
          {state.status === 'loading' ? 'Saving…' : `Load these ${scenario.props.length} memories into my account`}
        </button>
      )}
      {state.status === 'error' && <p className="error" role="alert">{state.text}</p>}
    </div>
  )
}

function runLabel(startedAt: string | null, index: number): string {
  if (!startedAt) return `Run ${index + 1}`
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(startedAt))
}

/**
 * One scenario's recorded run in the same chat, map and Inspect surfaces as a
 * live conversation. Nothing here can send a message or change an account.
 */
export function ScenarioReplay({ scenario, onBack, onHome, signedIn, onOpenLive }: Props) {
  const [runIndex, setRunIndex] = useState(0)
  const run = scenario.runs[runIndex] ?? scenario.runs[0]
  const { messages, timeline, memories } = useMemo(() => replayRun(scenario, run), [scenario, run])

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
            {scenario.runs.length > 1 && (
              <label className="replay-run-picker">
                Run
                <select value={runIndex} onChange={(event) => setRunIndex(Number(event.target.value))}>
                  {scenario.runs.map((item, index) => (
                    <option key={item.id} value={index}>{runLabel(item.startedAt, index)} · {item.passed}/{item.total}</option>
                  ))}
                </select>
              </label>
            )}
            <button type="button" className="quiet-button" onClick={onBack}>All scenarios</button>
          </div>
        </header>

        <section className="scenario-brief">
          <p className="eyebrow">{scenario.dated} · {run.model ?? 'model not recorded'}</p>
          <h2>{scenario.title}</h2>
          <p>{scenario.description}</p>
          <p className="scenario-result">
            <b>{run.passed}/{run.total} scenes passed</b>
            {run.ungraded > 0 && <> · {run.ungraded} ungraded</>}
            {run.executionFailures > 0 && <> · {run.executionFailures} execution {run.executionFailures === 1 ? 'fault' : 'faults'}</>}
            {run.logfireUrl && <> · <a href={run.logfireUrl} target="_blank" rel="noreferrer">Logfire</a></>}
          </p>
          {run.verdict && <p className="scenario-verdict"><span className="eyebrow">Reviewer's verdict</span>{run.verdict}</p>}
          <details>
            <summary>Who the reader is</summary>
            <p className="scenario-context">{scenario.context}</p>
          </details>
          {scenario.props.length > 0 && (
            <details>
              <summary>Placed in the account before the run ({scenario.props.length})</summary>
              <ul className="scenario-props">
                {scenario.props.map((prop) => <li key={prop.id}>{prop.text}</li>)}
              </ul>
              <LoadProps scenario={scenario} signedIn={signedIn} onOpenLive={onOpenLive} />
            </details>
          )}
        </section>

        <MessageList messages={messages} pending={false} />
        <p className="replay-bar">Recorded run · read-only. Replies are exactly what this build said; nothing is sent.</p>
      </section>

      <section className="analysis" aria-label="How this works">
        <Architecture
          key={run.id}
          timeline={timeline}
          progress={[]}
          pendingMessage={null}
          recordedMemories={{ rows: memories, note: RECORDED_MEMORY_NOTE }}
        />
      </section>
    </main>
  )
}
