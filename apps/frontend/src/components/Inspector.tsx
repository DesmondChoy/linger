import type { TurnTimeline } from '../types'

type Props = {
  timeline: TurnTimeline[]
}

function boundarySummary(turn: TurnTimeline) {
  const resolution = turn.contextResolution
  if (!resolution) return 'Checking what Linger can safely use.'
  if (resolution.status === 'confirmed') {
    return resolution.chapter_max
      ? `${resolution.work_title ?? resolution.work_id}, through completed chapter ${resolution.chapter_max}.`
      : `${resolution.work_title ?? resolution.work_id} confirmed; no completed chapter confirmed for this request.`
  }
  if (resolution.status === 'inferred') {
    return resolution.chapter_max
      ? `Likely scene: ${resolution.work_title}, Chapter ${resolution.chapter_max} — not a retrieval boundary.`
      : `Possible book: ${resolution.work_title}; chapter not inferred.`
  }
  return 'No book or reading position confirmed.'
}

function decisionSummary(turn: TurnTimeline) {
  const serendipity = turn.traces.find((trace) => trace.agent === 'Serendipity')
  if (turn.connection) return 'Serendipity found a tentative, evidence-backed connection.'
  if (serendipity?.status === 'declined' || serendipity?.status === 'skipped') {
    return 'No connection was released for this turn.'
  }
  if (serendipity) return serendipity.detail
  return 'Muse handled this as a direct reflection without a connection search.'
}

export function Inspector({ timeline }: Props) {
  return (
    <section className="inspector" aria-label="Agent activity inspector">
      <div className="inspector-heading">
        <p className="eyebrow">Inspect</p>
        <h2>How Linger handles each message</h2>
        <p>
          Each card is one reader message and its resulting reply. Linger separates an inferred book from a
          confirmed reading boundary. Muse is the only agent that writes to the reader; the other contracts are
          optional preparation steps you can open when you want the technical detail.
        </p>
        <p className="process-key">Reader message → context check → optional evidence hand-off → Muse draft → Provenance release decision</p>
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
              <li key={turn.id} className={`process-event ${turn.status}`}>
                <span className="event-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
                <details className="event-card" open={index === timeline.length - 1}>
                  <summary>
                    <span className="event-summary">
                      <span className="eyebrow">Reader message {String(index + 1).padStart(2, '0')}</span>
                      <strong>{turn.userInput}</strong>
                      <span>{boundarySummary(turn)}</span>
                      <small>{turn.status === 'complete' ? 'Reply complete' : turn.status}</small>
                    </span>
                    <span className="event-toggle" aria-hidden="true" />
                  </summary>

                  <div className="event-details">
                    <section>
                      <h4>What Linger knew</h4>
                      <p>{turn.contextResolution?.explanation ?? 'Waiting for the context check.'}</p>
                    </section>

                    <section>
                      <h4>Agents and decisions</h4>
                      <p>{decisionSummary(turn)}</p>
                      {turn.traces.length > 0 && (
                        <ul className="agent-traces">
                          {turn.traces.map((trace, traceIndex) => (
                            <li key={`${trace.agent}-${traceIndex}`}>
                              <b>{trace.agent}</b><span className={`trace-status ${trace.status}`}>{trace.status.replace('_', ' ')}</span><span>{trace.detail}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>

                    {turn.contract && (
                      <details className="raw-detail">
                        <summary>View MuseTurn contract</summary>
                        <pre>{JSON.stringify(turn.contract, null, 2)}</pre>
                      </details>
                    )}
                    {turn.contextResolution && (
                      <details className="raw-detail">
                        <summary>View context resolution: Router → MuseTurn</summary>
                        <pre>{JSON.stringify(turn.contextResolution, null, 2)}</pre>
                      </details>
                    )}
                    {turn.promptInspection && (
                      <details className="raw-detail">
                        <summary>View Muse dynamic input</summary>
                        <p className="muted">This is the request-scoped JSON contract passed to Muse.</p>
                        <pre>{turn.promptInspection.dynamic_input}</pre>
                      </details>
                    )}
                    {turn.connectionBrief && (
                      <details className="raw-detail">
                        <summary>View ConnectionBrief: Orchestrator → Serendipity</summary>
                        <pre>{JSON.stringify(turn.connectionBrief, null, 2)}</pre>
                      </details>
                    )}
                    {turn.librarianRequest && (
                      <details className="raw-detail">
                        <summary>View LibrarianRequest: Serendipity → Librarian</summary>
                        <pre>{JSON.stringify(turn.librarianRequest, null, 2)}</pre>
                      </details>
                    )}
                    {turn.evidenceBundle && (
                      <details className="raw-detail">
                        <summary>View EvidenceBundle: Librarian → Serendipity</summary>
                        <pre>{JSON.stringify(turn.evidenceBundle, null, 2)}</pre>
                      </details>
                    )}
                    {turn.release && (
                      <section>
                        <h4>Release decision</h4>
                        <p>
                          {turn.release.release_source === 'muse_candidate'
                            ? `Provenance approved the Muse candidate (${turn.release.provenance_verdicts.join(' → ')}).`
                            : 'The Muse candidate was withheld and the application supplied a safe decline.'}
                        </p>
                        {turn.release.failure_stage && <p className="muted">Failure stage: {turn.release.failure_stage.replace('_', ' ')}</p>}
                      </section>
                    )}
                    {turn.response && (
                      <section>
                        <h4>Response released to the reader</h4>
                        <p className="response-text">{turn.response}</p>
                      </section>
                    )}
                    {turn.connection && (
                      <section className="connection-decision">
                        <p className="eyebrow">Connection contract</p>
                        <h4>Serendipity proposed a thread to Muse</h4>
                        <p className="connection-byline">Librarian supplied permitted evidence; Muse decides whether and how to use this tentative thread in its response.</p>
                        <p>{turn.connection.tentative_claim}</p>
                        <p className="muted">Evidence: {turn.connection.evidence_ids.join(', ')} · {turn.connection.uncertainty} uncertainty</p>
                        {turn.connection.cultural_suggestion && (
                          <p className="muted">Optional cultural invitation: <a href={turn.connection.cultural_suggestion.source_url} target="_blank" rel="noreferrer">{turn.connection.cultural_suggestion.title} — {turn.connection.cultural_suggestion.creator}</a></p>
                        )}
                        <details className="raw-detail">
                          <summary>View ConnectionProposal: Serendipity → Muse</summary>
                          <pre>{JSON.stringify(turn.connection, null, 2)}</pre>
                        </details>
                      </section>
                    )}
                  </div>
                </details>
              </li>
            ))}
          </ol>
        )}
      </section>

      <p className="inspection-note">
        This prototype records the real request contract and prompt assembly. Connection proposals are inspection-only; Muse is the only agent that writes to the reader.
      </p>
    </section>
  )
}
