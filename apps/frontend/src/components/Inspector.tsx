import type { Connection, TurnTimeline } from '../types'

type Props = {
  timeline: TurnTimeline[]
}

function boundarySummary(turn: TurnTimeline) {
  const resolution = turn.contextResolution
  if (!resolution) return 'Checking what Linger can safely use.'
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
  return 'No book context; reflection and permitted memory or web connections remain available.'
}

function decisionSummary(turn: TurnTimeline) {
  if (turn.status === 'running') return 'This turn is still running. Live events below contain metadata only; the response remains private until review completes.'
  const serendipity = turn.traces.find((trace) => trace.agent === 'Serendipity')
  if (turn.connection) return 'Serendipity found a tentative, evidence-backed connection.'
  if (serendipity?.status === 'declined' || serendipity?.status === 'skipped') {
    return 'No connection was released for this turn.'
  }
  if (serendipity) return serendipity.detail
  return 'Muse handled this as a direct reflection without a connection search.'
}

function LiveProgress({ turn }: { turn: TurnTimeline }) {
  if (!turn.progressEvents.length) {
    return turn.status === 'running' ? <p className="muted">Waiting for the first server event…</p> : null
  }
  return (
    <ol className="live-progress" aria-label="Live safe processing metadata" aria-live="polite">
      {turn.progressEvents.map((event) => (
        <li key={event.sequence}>
          <span className="progress-time">{(event.elapsed_ms / 1000).toFixed(1)}s</span>
          <b>{event.agent} · {event.stage.replaceAll('_', ' ')}</b>
          <span className={`trace-status ${event.status}`}>{event.status}</span>
          <span>{event.detail}</span>
        </li>
      ))}
    </ol>
  )
}

function searchStatus(outcome: string) {
  if (outcome === 'evidence_found') return 'complete'
  if (outcome === 'no_evidence') return 'declined'
  return 'failed'
}

function searchDetail(search: NonNullable<TurnTimeline['serendipitySearches']>[number]) {
  const input = search.tool === 'get_page' ? search.request.url : search.request.query
  const requestText = typeof input === 'string' && input ? ` — ${input}` : ''
  const resultKind = search.tool === 'web_search' ? 'lead' : 'citable evidence record'
  const evidenceText = search.evidence_ids.length
    ? ` Returned ${search.evidence_ids.length} ${resultKind}${search.evidence_ids.length === 1 ? '' : 's'}.`
    : ` Returned no ${resultKind}s.`
  return `${search.tool}${requestText}. ${search.outcome.replaceAll('_', ' ')}.${evidenceText}`
}

function HandshakeFlow({ turn }: { turn: TurnTimeline }) {
  const serendipity = turn.traces.find((trace) => trace.agent === 'Serendipity')
  const invoked = Boolean(turn.connectionDiscoveryInput)
  const steps = [
    {
      from: 'Router',
      to: 'Muse',
      status: 'complete',
      detail: `Created MuseTurn with connection discovery ${turn.contract?.policy.allow_connection ? 'allowed' : 'disabled'}.`,
    },
    {
      from: 'Muse',
      to: 'Serendipity',
      status: invoked ? (serendipity?.status ?? 'complete') : 'skipped',
      detail: invoked
        ? `Called serendipity_explore with ${turn.connectionDiscoveryInput?.intent ?? 'find_connection'} intent.`
        : 'Muse did not call serendipity_explore.',
    },
    ...(turn.serendipitySearches ?? []).map((search) => ({
      from: 'Serendipity',
      to: search.source === 'web' ? 'Exa' : 'Librarian',
      status: searchStatus(search.outcome),
      detail: searchDetail(search),
    })),
    ...(invoked ? [{
      from: 'Serendipity',
      to: 'Muse',
      status: turn.connection ? 'complete' : 'declined',
      detail: turn.connection
        ? `Returned ConnectionProposal and selected ${turn.connection.selected_candidate_id}.`
        : `Returned ConnectionDecline: ${turn.connectionDecline?.reason?.replaceAll('_', ' ') ?? 'no proposal released'}.`,
    }] : []),
    {
      from: 'Muse',
      to: 'Provenance',
      status: turn.release ? 'complete' : 'failed',
      detail: turn.release
        ? `Submitted the candidate for review; verdict path ${turn.release.provenance_verdicts.join(' → ') || 'unavailable'}.`
        : 'No release record is available.',
    },
    {
      from: 'Provenance',
      to: 'Reader',
      status: turn.release?.release_source === 'muse_candidate' ? 'complete' : 'failed',
      detail: turn.release?.release_source === 'muse_candidate'
        ? 'Approved candidate released.'
        : 'Candidate withheld; application safe decline released.',
    },
  ]

  return (
    <ol className="handshake-flow">
      {steps.map((step, index) => (
        <li key={`${step.from}-${step.to}-${index}`}>
          <span className="handshake-route"><b>{step.from}</b><span aria-hidden="true">→</span><b>{step.to}</b></span>
          <span className={`trace-status ${step.status}`}>{step.status}</span>
          <span>{step.detail}</span>
        </li>
      ))}
    </ol>
  )
}

function ConnectionDeclineDecision({ turn }: { turn: TurnTimeline }) {
  const decline = turn.connectionDecline
  if (!decline) return null
  return (
    <section className="connection-decision declined">
      <p className="eyebrow">Connection contract</p>
      <h4>Serendipity declined to surface a connection</h4>
      <p>{decline.safe_next_step}</p>
      <p className="muted">Reason: {decline.reason.replaceAll('_', ' ')}</p>
      <details className="raw-detail">
        <summary>View ConnectionDecline: Serendipity → Muse</summary>
        <pre>{JSON.stringify(decline, null, 2)}</pre>
      </details>
    </section>
  )
}

function ConnectionDecision({ connection }: { connection: Connection }) {
  const selected = connection.shortlist.find(
    (candidate) => candidate.candidate_id === connection.selected_candidate_id,
  )
  if (!selected) return null

  return (
    <section className="connection-decision">
      <p className="eyebrow">Connection contract</p>
      <h4>Serendipity proposed a thread to Muse</h4>
      <p className="connection-byline">
        Serendipity searched permitted internal and web sources, removed ineligible evidence,
        compared {connection.shortlist.length} candidates, and selected rank 1. Muse decides
        whether and how to use that tentative thread in its response.
      </p>
      <p>{selected.tentative_claim}</p>
      <p className="muted">Evidence: {selected.evidence_ids.join(', ')} · {connection.uncertainty} uncertainty</p>
      <ol className="connection-shortlist">
        {connection.shortlist.map((candidate) => (
          <li key={candidate.candidate_id}>
            <b>#{candidate.rank} {candidate.tentative_claim}</b>
            <span>{candidate.comparison_note}</span>
            <small>
              cue {candidate.rubric.cue_fit} · reflection {candidate.rubric.reflective_value} ·
              safety {candidate.rubric.safety}
            </small>
          </li>
        ))}
      </ol>
      <details className="raw-detail">
        <summary>View ConnectionProposal: Serendipity → Muse</summary>
        <pre>{JSON.stringify(connection, null, 2)}</pre>
      </details>
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
          boundary enables spoiler-safe book retrieval, while reflection and permitted memory or web connections
          can proceed without one. Muse is the only agent that writes to the reader; the other contracts are
          optional preparation steps you can open when you want the technical detail.
        </p>
        <p className="process-key">Reader message → source grants → Serendipity searches Librarian / Exa → filter and compare 2–3 candidates → Muse draft → Provenance release decision</p>
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
                      <small>{turn.status === 'complete' ? 'Reply complete' : turn.status === 'running' ? 'Processing live…' : 'Request failed'}</small>
                    </span>
                    <span className="event-toggle" aria-hidden="true" />
                  </summary>

                  <div className="event-details">
                    <section>
                      <h4>{turn.status === 'running' ? 'Live process' : 'Process timing'}</h4>
                      <p className="muted">Safe metadata only—no prompt text, search terms, evidence, draft response, or review critique is streamed.</p>
                      <LiveProgress turn={turn} />
                    </section>
                    <section>
                      <h4>What Linger knew</h4>
                      <p>{turn.contextResolution?.explanation ?? 'Waiting for the context check.'}</p>
                    </section>

                    {turn.status !== 'running' && <section>
                      <h4>Agent handshakes</h4>
                      <p>{decisionSummary(turn)}</p>
                      <HandshakeFlow turn={turn} />
                      {turn.traces.length > 0 && (
                        <details className="raw-detail">
                          <summary>View agent status summary</summary>
                          <ul className="agent-traces">
                            {turn.traces.map((trace, traceIndex) => (
                              <li key={`${trace.agent}-${traceIndex}`}>
                                <b>{trace.agent}</b><span className={`trace-status ${trace.status}`}>{trace.status.replace('_', ' ')}</span><span>{trace.detail}</span>
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </section>}

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
                    {turn.connectionDiscoveryInput && (
                      <details className="raw-detail">
                        <summary>View ConnectionDiscoveryInput: Orchestrator → Serendipity</summary>
                        <pre>{JSON.stringify(turn.connectionDiscoveryInput, null, 2)}</pre>
                      </details>
                    )}
                    {!!turn.serendipitySearches?.length && (
                      <details className="raw-detail">
                        <summary>View searches chosen by Serendipity</summary>
                        <pre>{JSON.stringify(turn.serendipitySearches, null, 2)}</pre>
                      </details>
                    )}
                    {turn.librarianRequest && (
                      <details className="raw-detail">
                        <summary>View LibrarianRequest: Serendipity → Librarian</summary>
                        <pre>{JSON.stringify(turn.librarianRequest, null, 2)}</pre>
                      </details>
                    )}
                    {turn.librarianGrounding.length > 0 && (
                      <details className="raw-detail">
                        <summary>View direct grounding calls: Muse → Librarian</summary>
                        <p className="muted">
                          Routine book grounding Muse requested outside connection discovery.
                        </p>
                        <pre>{JSON.stringify(turn.librarianGrounding, null, 2)}</pre>
                      </details>
                    )}
                    {turn.evidenceBundle && (
                      <details className="raw-detail">
                        <summary>View retrieved evidence available to Serendipity</summary>
                        <pre>{JSON.stringify(turn.evidenceBundle, null, 2)}</pre>
                      </details>
                    )}
                    {turn.connection && <ConnectionDecision connection={turn.connection} />}
                    <ConnectionDeclineDecision turn={turn} />
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
