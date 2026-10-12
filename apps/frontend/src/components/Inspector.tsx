import type { CaptureInspection, ChatResult, ReleaseInspection, RiskCode, TurnRecord } from '../types'
import { museTurnView } from './architecture/turnDetail'
import { formatMachineLabel } from './formatMachineLabel'
import { formatSeconds, toAgentSteps, toAgentTotals } from './progressSummary'

type Props = {
  timeline: TurnRecord[]
  /** Which turn the map is showing, so the two stay in step. */
  selectedTurnId?: string
  onSelectTurn?: (turnId: string) => void
}

function AgentTiming({ turn }: { turn: TurnRecord }) {
  // A turn recorded before the stream produced anything still renders the rest
  // of the card rather than blanking the panel.
  const events = turn.progress ?? []
  const steps = toAgentSteps(events)
  if (!steps.length) return null
  const totals = toAgentTotals(steps)
  const wallClock = events[events.length - 1].elapsed_ms

  return (
    <section className="agent-timing">
      <h4>Agent timing and handoffs</h4>
      <p className="muted">
        Server-measured stage metadata only. Prompts, drafts, queries, and evidence never enter
        the progress stream.
      </p>

      <ul className="agent-totals">
        {totals.map((total) => (
          <li key={total.agent}>
            <b>{total.agent}</b>
            <span className="agent-total-time">
              {formatSeconds(total.durationMs)}
              {total.partial && '+'}
            </span>
            <small>{total.steps === 1 ? '1 stage' : `${total.steps} stages`}</small>
          </li>
        ))}
        <li className="agent-total-wall">
          <b>Turn</b>
          <span className="agent-total-time">{formatSeconds(wallClock)}</span>
          <small>wall clock</small>
        </li>
      </ul>

      <ol className="handshake-flow" aria-label="Agent interactions in order">
        {steps.map((step) => (
          <li key={step.key} className={step.status}>
            <span className="progress-time">{formatSeconds(step.startedMs)}</span>
            <span className="handshake-pair">
              {step.from} <span aria-hidden="true">→</span> {step.to}
            </span>
            <b>{step.agent} · {formatMachineLabel(step.stage)}</b>
            <span className={`trace-status ${step.status}`}>
              {formatMachineLabel(step.status)}
            </span>
            <span className="progress-duration">
              {step.durationMs === null ? '—' : formatSeconds(step.durationMs)}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
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
    const part = resolution.part_id === 'main' ? '' : ` in ${resolution.part_id === 'part-iii' ? 'Part III' : resolution.part_id.replaceAll('-', ' ')}`
    if (resolution.unit_ids.length > 0) {
      return `${resolution.work_title ?? resolution.work_id}, only the ${resolution.unit_ids.length === 1 ? 'named reading location' : 'named reading locations'} explicitly completed${part}; other material remains outside this reading boundary.`
    }
    if (resolution.boundary_source === 'librarian_inferred') {
      return `${resolution.work_title ?? resolution.work_id}, memory-supported ceiling Chapter ${resolution.chapter_max}${part} (${Math.round((resolution.boundary_confidence ?? 0) * 100)}% confidence).`
    }
    return resolution.chapter_max
      ? `${resolution.work_title ?? resolution.work_id}, through completed chapter ${resolution.chapter_max}${part}.`
      : `${resolution.work_title ?? resolution.work_id} confirmed; book retrieval is off, while reflection and other permitted connections remain available.`
  }
  if (resolution.status === 'inferred') {
    return `Possible book: ${resolution.work_title}; spoiler boundary not validated.`
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

function releaseLabel(turn: ChatResult) {
  switch (turn.inspection.release?.release_source) {
    case 'application_clarification':
      return 'Clarification requested'
    case 'application_safe_decline':
      return 'Safe decline released'
    case 'application_emotional_boundary':
      return 'Emotional boundary released'
    case 'application_language_boundary':
      return 'English-only notice released'
    default:
      return 'Reply complete'
  }
}

function releaseDecisionSummary(turn: ChatResult) {
  const source = turn.inspection.release?.release_source
  if (source === 'muse_candidate') {
    return `Provenance approved the Muse candidate (${turn.inspection.release?.provenance_verdicts.join(' → ')}).`
  }
  if (source === 'application_clarification') {
    return "The application delivered Librarian's validated question after safety review."
  }
  if (source === 'application_emotional_boundary') {
    return turn.inspection.release?.boundary_origin === 'preflight'
      ? 'The no-tool preflight required the fixed application-owned emotional boundary.'
      : 'Candidate review caught a preflight miss, withheld the Muse candidate, and required the fixed application-owned emotional boundary.'
  }
  if (source === 'application_language_boundary') {
    return 'The English-only language guard released the fixed notice before any model ran.'
  }
  if (turn.inspection.release?.failure_stage === 'emotional_boundary_preflight') {
    return 'The emotional-boundary preflight failed, so Muse was skipped and the application supplied a safe decline.'
  }
  return 'The Muse candidate was withheld and the application supplied a safe decline.'
}

// What each Provenance finding means for the reader, in plain language. These
// are the codes that explain why a candidate was revised or withheld, so they
// are the first thing worth reading when a turn ends in a safe decline.
const FINDING_EXPLANATIONS: Record<RiskCode, string> = {
  unresolved_evidence: 'The draft cited evidence the turn never actually retrieved.',
  misattribution: 'The draft attributed something to the wrong source.',
  spoiler: 'The draft reached past the confirmed reading boundary.',
  uncited_web_claim: 'The draft made a web-sourced claim without citing the page.',
  unsupported_claim: 'The draft asserted something no retrieved evidence supports.',
  sensitive_content: 'The draft handled sensitive material outside policy.',
  emotional_policy_violation: 'The draft breached the emotional boundary contract.',
  prompt_injection: 'Retrieved content tried to steer the agent.',
  policy_override: 'The draft complied with an attempt to override its instructions.',
  harmful_content: 'The draft contained toxic, dangerous, or hateful content.',
  false_persona: 'The draft claimed a human self or fostered dependence on the companion.',
  professional_advice: 'The draft gave individualised medical, legal, financial, or therapeutic advice.',
  out_of_scope: 'The draft performed a task unrelated to reflecting on the reading.',
  instruction_disclosure: "The draft revealed or paraphrased the companion's own instructions or tooling.",
}

function ReviewFindings({ release }: { release: ReleaseInspection }) {
  const verdicts = release.provenance_verdicts
  const survived = release.release_source === 'muse_candidate'

  if (!release.finding_codes.length) {
    return (
      <p className="muted">
        Review path: {verdicts.join(' → ') || 'unavailable'}. No findings were raised.
      </p>
    )
  }

  return (
    <div className="review-findings">
      <p className="muted">
        Review path: {verdicts.join(' → ') || 'unavailable'}
        {release.revision_count > 0 && ` · ${release.revision_count} revision${release.revision_count === 1 ? '' : 's'}`}
        {survived
          ? ' · the candidate was corrected and released.'
          : ' · the candidate was withheld.'}
      </p>
      <ul className="finding-codes">
        {release.finding_codes.map((code, index) => (
          <li key={`${code}-${index}`}>
            <b className={survived ? 'finding corrected' : 'finding blocking'}>
              {formatMachineLabel(code)}
            </b>
            <span>{FINDING_EXPLANATIONS[code] ?? 'Provenance raised this finding.'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function captureSummary(capture: CaptureInspection): string {
  const reason = capture.reason_code ? ` (${formatMachineLabel(capture.reason_code)})` : ''
  if (capture.storage === 'committed') {
    return capture.reason_code === 'idempotent_replay'
      ? 'This memory was already saved by an earlier attempt of the same turn.'
      : 'Muse proposed a memory, Provenance allowed it, and policy saved it.'
  }
  if (capture.nomination === 'no_candidate') return 'Muse did not propose anything to remember.'
  if (capture.nomination === 'unavailable') return 'No memory proposal was available for this turn.'
  if (capture.provenance_decision === 'reject_capture') return 'Muse proposed a memory; Provenance vetoed it.'
  if (capture.storage === 'suppressed') return `Muse proposed a memory; saving was suppressed${reason}.`
  if (capture.storage === 'refused') return `Muse proposed a memory; policy refused it${reason}.`
  return `No memory was saved${reason}.`
}

function MemoryActivity({ turn }: { turn: TurnRecord }) {
  const memory = turn.inspection.memory
  const capture = turn.inspection.release?.capture
  if (!memory && !capture) return null
  const ids = [
    ...(memory?.captured_memory_id ? [{ label: 'Saved this turn', id: memory.captured_memory_id }] : []),
    ...(memory?.cited_memory_ids ?? []).map((id) => ({ label: 'Used in the reply', id })),
  ]
  return (
    <section className="memory-activity">
      <h4>Memory</h4>
      {capture && <p>{captureSummary(capture)}</p>}
      {ids.length > 0 && (
        <ul className="memory-ids">
          {ids.map((item) => (
            <li key={`${item.label}-${item.id}`}>
              <b>{item.label}</b>
              {memory?.texts?.[item.id] && <blockquote>{memory.texts[item.id]}</blockquote>}
              <code>{item.id}</code>
            </li>
          ))}
        </ul>
      )}
      {memory && !turn.replayed && (
        <p className="muted">
          {memory.active_count === 1 ? '1 saved memory was' : `${memory.active_count} saved memories were`} available to this turn.
          {ids.length > 0 && !memory.texts && <> Memory text appears here when the server runs with <code>LINGER_DEV_INSPECT=true</code>, or read it with <code>uv run python -m apps.backend.show_memories &lt;username&gt; &lt;id&gt;</code>.</>}
        </p>
      )}
    </section>
  )
}

function ConnectionDeclineDecision({ turn }: { turn: ChatResult }) {
  const decline = turn.inspection.connection_decline
  if (!decline) return null
  return (
    <section className="connection-decision declined">
      <p className="eyebrow">Connection contract</p>
      <h4>Serendipity declined to surface a connection</h4>
      <p className="muted">Reason: {formatMachineLabel(decline.reason)}</p>
      {decline.failure_code && <p className="muted">Failure: connection discovery failed closed.</p>}
    </section>
  )
}

const ASSESSMENT_LABELS: Record<string, string> = {
  credible_pass: 'Credible pass',
  pass_with_limitations: 'Pass with limitations',
  potential_false_positive: 'Possible false pass',
  supported_failure: 'Real failure',
  potential_false_negative: 'Possible false failure',
  inconclusive: 'Inconclusive',
  not_exercised: 'Not exercised',
}

/** A recorded Scene's adopted answer key beside its result; replayed runs only. */
function AnswerKey({ grading }: { grading: NonNullable<TurnRecord['grading']> }) {
  return (
    <section className={`answer-key is-${grading.status}`}>
      <h4>Answer key <span className={`answer-status is-${grading.status}`}>{grading.status}</span></h4>
      <p className="muted">Written and adopted by a person before the run; the system never saw it.</p>
      {grading.expected.length > 0 && (
        <ul className="key-list">
          {grading.expected.map((text) => <li key={text}><b>must</b><span>{text}</span></li>)}
          {grading.prohibited.map((text) => <li key={text}><b className="prohibited">must not</b><span>{text}</span></li>)}
        </ul>
      )}
      {grading.executionFailures.length > 0 && (
        <p className="answer-execution">
          Execution fault, not a behaviour result: {grading.executionFailures.join('; ')}.
        </p>
      )}
      {grading.failures.length > 0 && (
        <p className="muted">Failed checks: {grading.failures.map(formatMachineLabel).join(', ')}.</p>
      )}
      {grading.assessment && (
        <div className="answer-review">
          <p className="eyebrow">Reviewer's assessment · {ASSESSMENT_LABELS[grading.assessment] ?? formatMachineLabel(grading.assessment)}</p>
          {grading.analysis && <p>{grading.analysis}</p>}
        </div>
      )}
    </section>
  )
}

/** The plain-language record of one turn: what happened, not the raw contracts. */
function TurnOutcome({ turn }: { turn: TurnRecord }) {
  return (
    <>
      {turn.grading && <AnswerKey grading={turn.grading} />}
      <section>
        <h4>What Linger knew</h4>
        <p>{turn.inspection.context_resolution.explanation}</p>
      </section>

      <AgentTiming turn={turn} />
      <section>
        <h4>Agents and decisions</h4>
        <p>{decisionSummary(turn)}</p>
        {turn.inspection.traces.length > 0 && (
          <ul className="agent-traces">
            {turn.inspection.traces.map((trace, traceIndex) => (
              <li key={`${trace.agent}-${traceIndex}`}>
                <b>{trace.agent}</b><span className={`trace-status ${trace.status}`}>{formatMachineLabel(trace.status)}</span><span>{trace.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <ConnectionDeclineDecision turn={turn} />
      {turn.inspection.release && (
        <section>
          <h4>Release decision</h4>
          <p>{releaseDecisionSummary(turn)}</p>
          {turn.inspection.release.failure_stage && <p className="muted">Failure stage: {formatMachineLabel(turn.inspection.release.failure_stage)}</p>}
          <ReviewFindings release={turn.inspection.release} />
        </section>
      )}
      <MemoryActivity turn={turn} />
    </>
  )
}

/** Pretty-print a JSON string so it reads as lines, not one long row. */
function readableJson(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch {
    return text
  }
}

/** The exact contracts behind one turn, for the full view. */
function TurnContracts({ turn }: { turn: TurnRecord }) {
  return (
    <>
      <details className="raw-detail">
        <summary>View MuseTurn contract</summary>
        <pre>{JSON.stringify(museTurnView(turn), null, 2)}</pre>
      </details>
      <details className="raw-detail">
        <summary>View context resolution: Router → MuseTurn</summary>
        <pre>{JSON.stringify(turn.inspection.context_resolution, null, 2)}</pre>
      </details>
      <details className="raw-detail">
        <summary>View assembled Muse dynamic input</summary>
        <p className="muted">This request-scoped JSON contract is passed to Muse only when the preflight allows reflection to continue.</p>
        <pre>{readableJson(turn.inspection.prompt)}</pre>
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
    </>
  )
}

/** One turn under the map: its outcome only, so it never reads as the whole history. */
export function TurnSummary({ turn, position }: { turn: TurnRecord; position: number }) {
  return (
    <section className="turn-summary" aria-label="This turn">
      <p className="eyebrow">Reader message {String(position + 1).padStart(2, '0')}</p>
      <h3>{turn.inspection.muse_turn.user_message}</h3>
      <p className="muted">
        {turn.grading?.offline
          ? 'Offline curation task · no reader message, nothing released'
          // A replayed turn states only what its run recorded, not live policy wording.
          : `${turn.replayed ? turn.inspection.context_resolution.explanation : boundarySummary(turn)} · ${releaseLabel(turn)}`}
      </p>
      <div className="event-details">
        <TurnOutcome turn={turn} />
      </div>
    </section>
  )
}

/** Every turn with its outcome and exact contracts: the full view. */
export function Inspector({ timeline, selectedTurnId, onSelectTurn }: Props) {
  return (
    <section className="inspector" aria-label="Agent activity inspector">
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
              <li key={turn.inspection.muse_turn.turn_id} className={`process-event ${turn.inspection.release?.release_source === 'application_safe_decline' ? 'declined' : 'complete'} ${turn.inspection.muse_turn.turn_id === selectedTurnId ? 'is-mapped' : ''}`}>
                <span className="event-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
                <details
                  className="event-card"
                  open={selectedTurnId
                    ? turn.inspection.muse_turn.turn_id === selectedTurnId
                    : index === timeline.length - 1}
                >
                  <summary onClick={() => onSelectTurn?.(turn.inspection.muse_turn.turn_id)}>
                    <span className="event-summary">
                      <span className="eyebrow">Reader message {String(index + 1).padStart(2, '0')}</span>
                      <strong>{turn.inspection.muse_turn.user_message}</strong>
                      <span>{boundarySummary(turn)}</span>
                      <small>{releaseLabel(turn)}</small>
                    </span>
                    <span className="event-toggle" aria-hidden="true" />
                  </summary>

                  <div className="event-details">
                    <TraceLink turn={turn} />
                    <TurnOutcome turn={turn} />
                    <TurnContracts turn={turn} />
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
        Inspect records the request contract, direct Librarian grounding, release decision, and fixed Serendipity outcome metadata. Muse drafts ordinary replies; fixed policy responses are application-owned.
      </p>
    </section>
  )
}
