import { useEffect, useState, type ReactNode } from 'react'

import { forgetMemory, listMemories } from '../api'
import type { AgentTrace, CaptureInspection, ChatResult, ReadingProgressEntry, ReleaseInspection, StoredMemory, ToolExposureInspection, TurnRecord } from '../types'
import { museTurnView } from './architecture/turnDetail'
import { FINDING_EXPLANATIONS } from './findingExplanations'
import { formatMachineLabel } from './formatMachineLabel'
import { formatSeconds, toAgentSteps, toAgentTotals } from './progressSummary'

type Props = {
  timeline: TurnRecord[]
  /** Which turn the map is showing, so the two stay in step. */
  selectedTurnId?: string
  onSelectTurn?: (turnId: string) => void
}

/** Matches the agent colours on the architecture map. */
function agentClass(agent: string) {
  return `agent-${agent.toLowerCase().replace(/[^a-z]+/g, '-')}`
}

function AgentName({ agent }: { agent: string }) {
  return <b className="agent-name"><span className={`agent-dot ${agentClass(agent)}`} aria-hidden="true" />{agent}</b>
}

/** Each stage as a bar on the turn's clock, so waits and overlaps are visible. */
function TurnTimeline({ turn }: { turn: TurnRecord }) {
  // A turn recorded before the stream produced anything still renders the rest
  // of the card rather than blanking the panel.
  const events = turn.progress ?? []
  const steps = toAgentSteps(events)
  if (!steps.length) return null
  const wallClock = events[events.length - 1].elapsed_ms
  const scale = Math.max(wallClock, 1)
  const totals = toAgentTotals(steps)
    .map((total) => `${total.agent} ${formatSeconds(total.durationMs)}${total.partial ? '+' : ''}`)
    .join(' · ')

  return (
    <section className="turn-timeline">
      <h4>How the turn ran</h4>
      <div className="stage-row stage-head" aria-hidden="true">
        <span>Stage</span>
        <span className="stage-axis"><span>0s</span><span>{formatSeconds(wallClock)}</span></span>
        <span>Took</span>
      </div>
      <ol className="stage-rows" aria-label="Agent stages in order">
        {steps.map((step) => (
          <li key={step.key} className={`stage-row is-${step.status}`}>
            <span className="stage-name">
              <AgentName agent={step.agent} />
              <span>{formatMachineLabel(step.stage)}</span>
              {step.from !== 'Application' && step.from !== step.agent && <small>called by {step.from}</small>}
              {step.status !== 'complete' && (
                <span className={`trace-status ${step.status}`}>{formatMachineLabel(step.status)}</span>
              )}
            </span>
            <span className="stage-track" title={`Started at ${formatSeconds(step.startedMs)}`}>
              <span
                className={`stage-bar ${agentClass(step.agent)}${step.durationMs === null ? ' is-instant' : ''}`}
                style={{ left: `${(step.startedMs / scale) * 100}%`, width: `${((step.durationMs ?? 0) / scale) * 100}%` }}
              />
            </span>
            <span className="stage-time">{step.durationMs === null ? '—' : formatSeconds(step.durationMs)}</span>
          </li>
        ))}
      </ol>
      <p className="muted">
        Time per agent: {totals}. Overlapping bars mean an agent was waiting on one it called.
        Timing metadata only; prompts and text never enter this stream.
      </p>
    </section>
  )
}

/** The turn's three headline facts: what it could reveal, how it ended, how long it took. */
function TurnFacts({ turn }: { turn: TurnRecord }) {
  const resolution = turn.inspection.context_resolution
  const release = turn.inspection.release
  const events = turn.progress ?? []
  const findings = release?.finding_codes.length ?? 0
  return (
    <dl className="turn-facts">
      <div>
        <dt>Reading boundary</dt>
        {/* A replayed turn states only what its run recorded, not live policy wording. */}
        <dd>{turn.replayed ? resolution.explanation : boundarySummary(turn)}</dd>
        {!turn.replayed && <dd className="muted">{resolution.explanation}</dd>}
      </div>
      <div>
        <dt>Outcome</dt>
        <dd>{releaseLabel(turn)}</dd>
        {release && (
          <dd className="muted">
            {release.provenance_verdicts.length
              ? `Provenance: ${release.provenance_verdicts.join(' → ')}, ${findings === 0 ? 'no findings' : `${findings} finding${findings === 1 ? '' : 's'}`}.`
              : 'No Provenance review ran.'}
          </dd>
        )}
      </div>
      {events.length > 0 && (
        <div>
          <dt>Time</dt>
          <dd>{formatSeconds(events[events.length - 1].elapsed_ms)}</dd>
          <dd className="muted">Wall clock, end to end.</dd>
        </div>
      )}
    </dl>
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

const MEMORY_NEED_LABELS: Record<NonNullable<ToolExposureInspection['triage']>['memory'], string> = {
  own_earlier_reflections: 'your earlier reflections',
  named_sources: 'named sources',
  source_comparison: 'a source comparison',
  outside_recommendation: 'an outside recommendation',
  none: 'none',
  unsure: 'unsure',
}

/** Triage's reading of the message, then the tools Muse got and why. */
function TriageDecision({ exposure }: { exposure: ToolExposureInspection }) {
  const { triage } = exposure
  const bookTools = exposure.tools.filter((tool) => tool.startsWith('librarian_'))
  const carried = exposure.carried_tools ?? []
  const bookReason = !triage || triage.book_content !== 'no' || bookTools.length === 0
    ? null
    : exposure.book_override
      ? 'Book tools were offered anyway: this turn has a reading boundary or an open reading question.'
      : bookTools.every((tool) => carried.includes(tool))
        ? 'Book tools were offered anyway: an earlier turn in this conversation used them.'
        : null
  return (
    <>
      <p>
        {triage
          ? `Needs book content: ${triage.book_content} · Needs memory: ${MEMORY_NEED_LABELS[triage.memory]} · Override attempt: ${triage.override_attempt === 'attempted' ? 'yes' : 'no'}.`
          : 'Triage failed, so Muse was offered the book tools only.'}
      </p>
      <p className="tool-list">
        Muse was offered: {exposure.tools.length ? exposure.tools.map((tool) => <code key={tool}>{tool}</code>) : 'no tools'}
        {exposure.pinned_intent && <> · pinned intent <code>{exposure.pinned_intent}</code></>}
      </p>
      {bookReason && <p className="muted">{bookReason}</p>}
    </>
  )
}

function ReleaseDecision({ release, turn }: { release: ReleaseInspection; turn: ChatResult }) {
  return (
    <>
      <p>{releaseDecisionSummary(turn)}</p>
      {release.failure_stage && <p className="muted">Failure stage: {formatMachineLabel(release.failure_stage)}</p>}
      <ReviewFindings release={release} />
    </>
  )
}

type Decision = { key: string; agent: string; status: AgentTrace['status']; body: ReactNode }

/**
 * One row per agent that acted. The boundary and memory have their own
 * sections, the release folds into Provenance, and idle agents share one line.
 */
function AgentDecisions({ turn }: { turn: TurnRecord }) {
  const { traces, release, tool_exposure: exposure, context_resolution: resolution } = turn.inspection
  const decisions: Decision[] = []
  const idle: AgentTrace[] = []
  let releaseShown = false
  traces.forEach((trace, index) => {
    const key = `${trace.agent}-${index}`
    if (trace.agent === 'Router' && trace.detail === resolution.explanation) return
    if (trace.agent === 'Memory & Policy' && release?.capture) return
    if (trace.status === 'skipped' || trace.status === 'not_run') {
      idle.push(trace)
    } else if (trace.agent === 'Router' && exposure && trace.detail.startsWith('Turn triage')) {
      decisions.push({ key, agent: 'Triage', status: trace.status, body: <TriageDecision exposure={exposure} /> })
    } else if (trace.agent === 'Provenance' && release) {
      releaseShown = true
      decisions.push({ key, agent: 'Provenance', status: trace.status, body: <ReleaseDecision release={release} turn={turn} /> })
    } else {
      decisions.push({ key, agent: trace.agent, status: trace.status, body: <p>{trace.detail}</p> })
    }
  })
  if (release && !releaseShown) {
    decisions.push({ key: 'release', agent: 'Release', status: 'complete', body: <ReleaseDecision release={release} turn={turn} /> })
  }
  if (!decisions.length && !idle.length) return null
  return (
    <section className="agent-decisions">
      <h4>What each agent decided</h4>
      <ul className="decision-list">
        {decisions.map((decision) => (
          <li key={decision.key}>
            <span className="decision-agent">
              <AgentName agent={decision.agent} />
              {decision.status !== 'complete' && (
                <span className={`trace-status ${decision.status}`}>{formatMachineLabel(decision.status)}</span>
              )}
            </span>
            <div className="decision-body">{decision.body}</div>
          </li>
        ))}
      </ul>
      {idle.length > 0 && (
        <p className="muted idle-agents">
          Not used: {idle.map((trace, index) => (
            <span key={`${trace.agent}-${index}`}>{index > 0 && '; '}<b>{trace.agent}</b>, {trace.detail.replace(/\.$/, '')}</span>
          ))}.
        </p>
      )}
    </section>
  )
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
function ReviewFindings({ release }: { release: ReleaseInspection }) {
  const verdicts = release.provenance_verdicts
  const survived = release.release_source === 'muse_candidate'

  if (!release.finding_codes.length) {
    // A released candidate's summary already states its review path.
    return (
      <p className="muted">
        {!survived && `Review path: ${verdicts.join(' → ') || 'unavailable'}. `}No findings were raised.
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

// What Sculptor did after this turn's save; curation runs only for a fresh save.
const CURATION_SUMMARIES: Record<string, string> = {
  no_relevant_prior_memory: 'Sculptor did not run: no earlier memory shares a word with this one.',
  no_change: 'Sculptor looked at this memory beside related ones and proposed no change.',
  provenance_revise: 'Sculptor proposed a change; Provenance asked for a revision, and curation does not retry, so nothing was applied.',
  provenance_reject: 'Sculptor proposed a change; Provenance rejected it.',
  applied: 'Sculptor proposed a change, Provenance allowed it, and it was applied. See the Memories table.',
  failed: 'Sculptor curation failed; the saved memory is unaffected.',
}

/** Content hashes make IDs long; the full ID stays one hover away. */
function MemoryId({ id }: { id: string }) {
  return id.length > 20 ? <code title={id}>{id.slice(0, 16)}…</code> : <code>{id}</code>
}

const CURATION_ACTION_LABELS: Record<string, string> = {
  link_duplicates: 'Link as duplicates',
  update_derived_summary: 'Summary',
  assign_topic_group: 'Topic group',
  tombstone_for_retrieval: 'Retire a duplicate',
  restore_to_retrieval: 'Restore to search',
}

type CurationRecord = {
  proposal: { action: string; text?: string; sources: string[] } | { reason: string }
  review: { decision: string; findings: { code: string; explanation: string }[] } | null
}

/** What Sculptor proposed and Provenance decided; recorded only under developer inspect. */
function curationRecord(turn: TurnRecord): CurationRecord | null {
  const exchanges = turn.inspection.dev_trace?.agent_exchanges ?? []
  const output = exchanges.find((item) => item.role === 'Sculptor' && item.stage === 'curation')?.output as
    | { kind: 'curation_proposal'; action: Record<string, unknown> }
    | { kind: 'no_curation_proposal'; reason: string }
    | undefined
  if (!output) return null
  const reviewed = exchanges.find((item) => item.role === 'Provenance' && item.stage === 'curation_review')?.output as
    | { decision: string; findings?: { code: string; explanation: string }[] }
    | undefined
  const review = reviewed ? { decision: reviewed.decision, findings: reviewed.findings ?? [] } : null
  if (output.kind === 'no_curation_proposal') return { proposal: { reason: output.reason }, review }
  const action = output.action
  const sources = Array.isArray(action.source_memory_ids) ? action.source_memory_ids.map(String) : [String(action.memory_id)]
  const text = action.topic_label ?? action.summary
  return { proposal: { action: String(action.action), text: text === undefined ? undefined : String(text), sources }, review }
}

function CurationProposalDetail({ record }: { record: CurationRecord }) {
  const { proposal, review } = record
  if ('reason' in proposal) {
    return <p className="muted">Sculptor proposed no change: {proposal.reason}</p>
  }
  return (
    <div className="curation-proposal">
      <p className="memory-list-title">
        Sculptor proposed: {CURATION_ACTION_LABELS[proposal.action] ?? formatMachineLabel(proposal.action)}
        {proposal.text && <> “{proposal.text}”</>}
      </p>
      <p className="memory-id-line">Over {proposal.sources.map((id) => <code key={id}>{id}</code>)}</p>
      {review && (
        <>
          <p className="muted">Provenance: {formatMachineLabel(review.decision)}</p>
          {review.findings.length > 0 && (
            <ul className="finding-codes">
              {review.findings.map((finding, index) => (
                <li key={`${finding.code}-${index}`}>
                  <b className="finding blocking">{formatMachineLabel(finding.code)}</b>
                  <span>{finding.explanation}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

/** Per-turn memory: only which IDs this turn saved, used, and could search. The memory table holds the entries. */
function MemoryActivity({ turn }: { turn: TurnRecord }) {
  const memory = turn.inspection.memory
  const capture = turn.inspection.release?.capture
  if (!memory && !capture) return null
  const searchable = memory?.available_memories
  const curation = curationRecord(turn)
  const groups = [
    { label: 'Saved this turn', ids: memory?.captured_memory_id ? [memory.captured_memory_id] : [] },
    { label: 'Used in the reply', ids: memory?.cited_memory_ids ?? [] },
    { label: 'Searchable this turn', ids: (searchable ?? []).map((item) => item.memory_id) },
  ].filter((group) => group.ids.length > 0)
  return (
    <section className="memory-activity">
      <h4>Memory</h4>
      {capture && <p>{captureSummary(capture)}</p>}
      {capture?.curation_status && CURATION_SUMMARIES[capture.curation_status] && (
        <p className="muted">{CURATION_SUMMARIES[capture.curation_status]}</p>
      )}
      {curation && <CurationProposalDetail record={curation} />}
      {groups.length > 0 && (
        <dl className="memory-id-groups">
          {groups.map((group) => (
            <div key={group.label}>
              <dt>{group.label}</dt>
              <dd>{group.ids.map((id) => <MemoryId key={id} id={id} />)}</dd>
            </div>
          ))}
        </dl>
      )}
      {memory && !turn.replayed && searchable?.length === 0 && (
        <p className="muted">No memories were searchable this turn.</p>
      )}
      {memory && !turn.replayed && !searchable && (
        <p className="muted">
          {memory.active_count === 1 ? '1 saved memory was' : `${memory.active_count} saved memories were`} available to this turn.
        </p>
      )}
    </section>
  )
}

const MEMORY_KIND_LABELS: Record<StoredMemory['kind'], string> = {
  original: 'Original',
  derived_summary: 'Summary',
  topic_group: 'Topic group',
}

function formatStoredAt(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

/** Where a memory came from: the reader message that saved it, or the originals a curated item covers. */
function memorySource(row: StoredMemory, turnPosition: Map<string, number>): string {
  if (row.kind !== 'original') return `Curated from ${row.source_memory_ids.join(', ')}`
  const position = row.source_turn_id === null ? undefined : turnPosition.get(row.source_turn_id)
  return position === undefined ? 'Another conversation' : `Reader message ${String(position + 1).padStart(2, '0')}`
}

type MemoryTableViewProps = {
  rows: StoredMemory[]
  timeline: TurnRecord[]
  /** The memory being forgotten right now, so its button can say so. */
  forgetting: string | null
  onForget: (row: StoredMemory) => void
}

export function MemoryTableView({ rows, timeline, forgetting, onForget }: MemoryTableViewProps) {
  const turnPosition = new Map(timeline.map((turn, index) => [turn.inspection.muse_turn.turn_id, index]))
  const showText = rows.some((row) => row.text !== null)
  return (
    <section className="memory-table" aria-label="Saved memories">
      <p className="muted">
        {rows.length} {rows.length === 1 ? 'memory' : 'memories'}, {rows.filter((row) => !row.searchable).length} retired.
        Curation can retire an original and search a summary or topic group over it instead.
        Forgetting a memory also removes every summary or topic group built over it.
      </p>
      {rows.length === 0 ? (
        <p className="empty">Nothing is saved yet.</p>
      ) : (
        <div className="memory-table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Stored</th>
                <th scope="col">Memory ID</th>
                <th scope="col">Kind</th>
                <th scope="col">Source</th>
                <th scope="col">Status</th>
                {showText && <th scope="col">Memory</th>}
                <th scope="col"><span className="visually-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.memory_id} className={row.searchable ? undefined : 'is-retired'}>
                  <td><time dateTime={row.created_at}>{formatStoredAt(row.created_at)}</time></td>
                  <td><code>{row.memory_id}</code></td>
                  <td>{MEMORY_KIND_LABELS[row.kind]}{row.kind === 'topic_group' && row.text === null && row.topic_labels.length > 0 && ` · ${row.topic_labels.join(', ')}`}</td>
                  <td>{memorySource(row, turnPosition)}</td>
                  <td>
                    <span className={`memory-tag ${row.searchable ? 'is-available' : 'is-unavailable'}`}>
                      {row.searchable ? 'Searchable' : 'Retired'}
                    </span>
                  </td>
                  {showText && <td className="memory-text">{row.text ?? '—'}</td>}
                  <td>
                    {row.kind === 'original' && (
                      <button
                        type="button"
                        className="quiet-button memory-forget"
                        disabled={forgetting !== null}
                        onClick={() => onForget(row)}
                      >
                        {forgetting === row.memory_id ? 'Forgetting…' : 'Forget'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > 0 && !showText && (
        <p className="muted">
          Memory text appears here when the server runs with <code>LINGER_DEV_INSPECT=true</code>, or read it with <code>uv run python -m apps.backend.show_memories &lt;username&gt; &lt;id&gt;</code>.
        </p>
      )}
    </section>
  )
}

/** The signed-in reader's memories, read live from the store; each turn lists only the IDs it touched. */
export function MemoryTable({ timeline }: { timeline: TurnRecord[] }) {
  const [rows, setRows] = useState<StoredMemory[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [forgetting, setForgetting] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listMemories()
      .then((loaded) => { if (!cancelled) setRows(loaded) })
      .catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)) })
    return () => { cancelled = true }
  }, [])

  const forget = async (row: StoredMemory) => {
    const label = row.text ? `“${row.text}”` : row.memory_id
    if (!window.confirm(`Forget ${label}? Any summary or topic group built over it is removed too. This cannot be undone.`)) return
    setForgetting(row.memory_id)
    setError(null)
    try {
      await forgetMemory(row.memory_id)
      setRows(await listMemories())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setForgetting(null)
    }
  }

  return (
    <>
      {error && <p className="empty" role="alert">{error}</p>}
      {rows === null
        ? !error && <p className="muted">Loading memories…</p>
        : <MemoryTableView rows={rows} timeline={timeline} forgetting={forgetting} onForget={(row) => void forget(row)} />}
    </>
  )
}

function progressLabel(entry: ReadingProgressEntry) {
  if (entry.chapter_max === null) return 'Retracted; no chapter granted'
  const part = entry.part_id === 'main' ? '' : ` (${entry.part_id === 'part-iii' ? 'Part III' : entry.part_id.replaceAll('-', ' ')})`
  return `Chapter ${entry.chapter_max}${part}`
}

/** The stored chapter ceilings as the latest turn recorded them; separate from memories. */
export function ReadingStateTable({ timeline }: { timeline: TurnRecord[] }) {
  const asOf = timeline.findLastIndex((turn) => turn.inspection.reading_state)
  if (asOf < 0) {
    return <p className="empty">No turn here recorded reading progress. Send a message to record it.</p>
  }
  const state = timeline[asOf].inspection.reading_state!
  const rows = [
    ...(state.session ? [{ store: 'This conversation', entry: state.session }] : []),
    ...(state.saved ?? []).map((entry) => ({ store: 'Saved to account', entry })),
  ]
  return (
    <section className="memory-table" aria-label="Reading progress">
      <p className="muted">
        As recorded after reader message {String(asOf + 1).padStart(2, '0')}. Only chapters you stated are stored, never ones the Librarian inferred.
        This conversation holds one book at a time; saved progress applies again once you mention that book.
      </p>
      {rows.length === 0 ? (
        <p className="empty">No reading progress is stored yet.</p>
      ) : (
        <div className="memory-table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Store</th>
                <th scope="col">Book</th>
                <th scope="col">Completed</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ store, entry }) => (
                <tr key={`${store}-${entry.work_id}`}>
                  <td>{store}</td>
                  <td>{entry.title ?? <code>{entry.work_id}</code>}</td>
                  <td>{progressLabel(entry)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {state.saved === null && <p className="muted">This turn ran without the account store, so saved progress is not shown.</p>}
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
      {!turn.grading?.offline && <TurnFacts turn={turn} />}
      <TurnTimeline turn={turn} />
      <AgentDecisions turn={turn} />
      <ConnectionDeclineDecision turn={turn} />
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
      {turn.grading?.offline && <p className="muted">Offline curation task · no reader message, nothing released</p>}
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
