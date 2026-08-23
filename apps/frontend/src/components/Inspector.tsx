import type { ChatResult } from '../types'

type Props = {
  timeline: ChatResult[]
}

function TraceLink({ turn }: { turn: ChatResult }) {
  const query = `trace_id = '${turn.trace.trace_id}'`

  return (
    <section className="operational-trace">
      <h4>Operational trace</h4>
      <p className="muted">
        Server-generated correlation only. Reader messages, prompts, and responses are not sent to Logfire.
      </p>
      <code>{turn.trace.trace_id}</code>
      <div className="trace-actions">
        <button
          className="quiet-button"
          type="button"
          onClick={() => void navigator.clipboard.writeText(query)}
        >
          Copy trace query
        </button>
      </div>
    </section>
  )
}

function boundarySummary(turn: ChatResult) {
  const resolution = turn.inspection.context_resolution
  if (resolution.status === 'confirmed') {
    return resolution.chapter_max
      ? `${resolution.work_title ?? resolution.work_id}, through completed chapter ${resolution.chapter_max}.`
      : `${resolution.work_title ?? resolution.work_id} confirmed; book retrieval is off, while reflection and other permitted connections remain available.`
  }
  if (resolution.status === 'inferred') {
    return resolution.chapter_max
      ? `Likely scene: ${resolution.work_title}, Chapter ${resolution.chapter_max} — not a retrieval boundary.`
      : `Possible book: ${resolution.work_title}; chapter not inferred.`
  }
  return 'No book context; reflection and permitted public-web connections remain available.'
}

function decisionSummary(turn: ChatResult) {
  const serendipity = turn.inspection.traces.find((trace) => trace.agent === 'Serendipity')
  if (serendipity?.status === 'declined' || serendipity?.status === 'skipped' || serendipity?.status === 'failed') {
    return 'No connection was released for this turn.'
  }
  if (serendipity) return serendipity.detail
  return 'Muse handled this as a direct reflection without a connection search.'
}

function ConnectionDeclineDecision({ turn }: { turn: ChatResult }) {
  const decline = turn.inspection.connection_decline
  if (!decline) return null
  return (
    <section className="connection-decision declined">
      <p className="eyebrow">Connection contract</p>
      <h4>Serendipity declined to surface a connection</h4>
      <p className="muted">Reason: {decline.reason.replaceAll('_', ' ')}</p>
      {decline.failure_code && <p className="muted">Failure: connection discovery failed closed.</p>}
    </section>
  )
}

export function Inspector({ timeline }: Props) {
  return (
    <section className="inspector" aria-label="Agent activity inspector">
      <div className="inspector-heading">
        <p className="eyebrow">Inspect</p>
        <h2>How Linger handles each message</h2>
        <p>
          Each card is one message and its resulting reply. Books are optional context: a confirmed reading
          boundary enables spoiler-safe book retrieval, while reflection and permitted public-web connections
          can proceed without one. Muse is the only agent that writes to the reader; Inspect exposes only
          approved contracts and fixed metadata for withheld connection attempts.
        </p>
        <p className="process-key">Reader message → source grants → Muse → optional Serendipity handoff → Provenance release decision</p>
      </div>

      <section className="process-timeline" aria-label="Turn-by-turn processing timeline">
        <div className="timeline-heading">
          <p className="eyebrow">Processing timeline</p>
          <h3>What happened for each input</h3>
          <p>Open a message to see the plain-language outcome first, then the exact contracts and prompt behind it.</p>
        </div>

        {timeline.length === 0 ? (
          <p className="empty">Send a message to create the first recorded turn.</p>
        ) : (
          <ol>
            {timeline.map((turn, index) => (
              <li key={turn.inspection.muse_turn.turn_id} className={`process-event ${turn.inspection.release?.release_source === 'application_safe_decline' ? 'declined' : 'complete'}`}>
                <span className="event-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
                <details className="event-card" open={index === timeline.length - 1}>
                  <summary>
                    <span className="event-summary">
                      <span className="eyebrow">Reader message {String(index + 1).padStart(2, '0')}</span>
                      <strong>{turn.inspection.muse_turn.user_message}</strong>
                      <span>{boundarySummary(turn)}</span>
                      <small>{turn.inspection.release?.release_source === 'application_safe_decline' ? 'Safe decline released' : 'Reply complete'}</small>
                    </span>
                    <span className="event-toggle" aria-hidden="true" />
                  </summary>

                  <div className="event-details">
                    <TraceLink turn={turn} />
                    <section>
                      <h4>What Linger knew</h4>
                      <p>{turn.inspection.context_resolution.explanation}</p>
                    </section>

                    <section>
                      <h4>Agents and decisions</h4>
                      <p>{decisionSummary(turn)}</p>
                      {turn.inspection.traces.length > 0 && (
                        <ul className="agent-traces">
                          {turn.inspection.traces.map((trace, traceIndex) => (
                            <li key={`${trace.agent}-${traceIndex}`}>
                              <b>{trace.agent}</b><span className={`trace-status ${trace.status}`}>{trace.status.replace('_', ' ')}</span><span>{trace.detail}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>

                    <details className="raw-detail">
                      <summary>View MuseTurn contract</summary>
                      <pre>{JSON.stringify(turn.inspection.muse_turn, null, 2)}</pre>
                    </details>
                    <details className="raw-detail">
                      <summary>View context resolution: Router → MuseTurn</summary>
                      <pre>{JSON.stringify(turn.inspection.context_resolution, null, 2)}</pre>
                    </details>
                    <details className="raw-detail">
                      <summary>View Muse dynamic input</summary>
                      <p className="muted">This is the request-scoped JSON contract passed to Muse.</p>
                      <pre>{turn.inspection.prompt}</pre>
                    </details>
                    {turn.inspection.librarian_grounding.length > 0 && (
                      <details className="raw-detail">
                        <summary>View direct grounding calls: Muse → Librarian</summary>
                        <p className="muted">
                          Routine book grounding Muse requested outside connection discovery.
                        </p>
                        <pre>{JSON.stringify(turn.inspection.librarian_grounding, null, 2)}</pre>
                      </details>
                    )}
                    <ConnectionDeclineDecision turn={turn} />
                    {turn.inspection.release && (
                      <section>
                        <h4>Release decision</h4>
                        <p>
                          {turn.inspection.release.release_source === 'muse_candidate'
                            ? `Provenance approved the Muse candidate (${turn.inspection.release.provenance_verdicts.join(' → ')}).`
                            : 'The Muse candidate was withheld and the application supplied a safe decline.'}
                        </p>
                        {turn.inspection.release.failure_stage && <p className="muted">Failure stage: {turn.inspection.release.failure_stage.replace('_', ' ')}</p>}
                      </section>
                    )}
                    <section>
                      <h4>Response released to the reader</h4>
                      <p className="response-text">{turn.reply}</p>
                    </section>
                  </div>
                </details>
              </li>
            ))}
          </ol>
        )}
      </section>

      <p className="inspection-note">
        Inspect records the request contract, direct Librarian grounding, release decision, and fixed Serendipity outcome metadata. Muse is the only agent that writes to the reader.
      </p>
    </section>
  )
}
