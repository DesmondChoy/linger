import type { ComponentId } from '@linger/architecture-map'
import type { AgentExchange, RiskCode, TurnRecord } from '../../types'
import { FINDING_EXPLANATIONS } from '../findingExplanations'
import { formatMachineLabel } from '../formatMachineLabel'
import { INTENTS, count, finish, quote, type Story } from './connectionStory'

/**
 * Each agent's recorded runs on one turn, retold for a reader: what it was
 * asked, what it decided, and what that meant for the reply. Developer inspect
 * only; the raw runs stay below it. Serendipity has its own retelling built
 * from its search events.
 */

type Fields = Record<string, unknown>

function fields(value: unknown): Fields {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Fields : {}
}

function text(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined
}

function items<T = Fields>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : []
}

function sure(confidence: unknown): string {
  return typeof confidence === 'number' ? `${Math.round(confidence * 100)}% sure` : 'confidence not recorded'
}

function stageName(run: AgentExchange): string {
  return formatMachineLabel(run.stage)
}

function failedStep(run: AgentExchange): string {
  return `${run.role}'s ${stageName(run)} run did not finish (${formatMachineLabel(run.failure_code ?? run.status)}).`
}

function genericStep(run: AgentExchange): string {
  return `${run.role} ran ${stageName(run)}.`
}

// ---------------------------------------------------------------- Provenance

const PREFLIGHT_DECISIONS: Record<string, string> = {
  continue_reflection: 'found no sign of distress, so the turn carried on as normal.',
  apply_boundary: 'found signs of distress, so Linger answered with a fixed, supportive message instead of reflecting on the book.',
  apply_self_harm_boundary: 'found signs of possible self-harm, so Linger answered with a fixed safety message instead of reflecting on the book.',
}

function preflightStory(runs: AgentExchange[]): Story {
  const steps = runs.map((run) => {
    if (run.status !== 'success') return failedStep(run)
    const decision = text(fields(run.output).decision) ?? ''
    return `Before anything else ran, Provenance read your message for signs of distress and ${PREFLIGHT_DECISIONS[decision] ?? `decided “${formatMachineLabel(decision)}”.`}`
  })
  const decision = text(fields(runs.at(-1)?.output).decision)
  return {
    summary: decision === 'continue_reflection'
      ? 'No sign of distress, so the turn carried on.'
      : decision ? 'Signs of distress, so Linger sent a fixed boundary message.' : 'The distress check did not finish.',
    steps,
  }
}

type Finding = { code: string; explanation?: string }

/** A finding's plain meaning, then the reviewer's own reason for this draft. */
function findingText(finding: Finding): string {
  const meaning = FINDING_EXPLANATIONS[finding.code as RiskCode] ?? `${formatMachineLabel(finding.code)}.`
  return finding.explanation ? `${meaning} Its reason: ${finish(quote(finding.explanation, 260))}` : meaning
}

const CAPTURE_DECISIONS: Record<string, string> = {
  allow_capture: ' It allowed the proposed memory to be saved.',
  reject_capture: ' It did not allow the proposed memory to be saved.',
}

function reviewStory(runs: AgentExchange[]): Story {
  const decisions: string[] = []
  const steps = runs.map((run, position) => {
    if (run.status !== 'success') return failedStep(run)
    const review = fields(run.output)
    const decision = text(review.response_decision) ?? ''
    decisions.push(decision)
    const which = position === 0 ? 'the draft' : `revision ${position}`
    const findings = items<Finding>(review.findings).map(findingText)
    const verdict = {
      pass: `Provenance checked ${which} against the evidence and passed it.`,
      revise: `Provenance checked ${which} and sent it back to Muse to fix.`,
      reject: `Provenance checked ${which} and blocked it.`,
    }[decision] ?? `Provenance checked ${which} and decided “${formatMachineLabel(decision)}”.`
    const boundary = review.emotional_boundary_decision === 'required'
      ? ' It judged that a supportive boundary message was needed instead.'
      : ''
    const findingList = findings.length ? ` ${findings.join(' ')}` : ''
    return `${verdict}${findingList}${boundary}${CAPTURE_DECISIONS[text(review.capture_decision) ?? ''] ?? ''}`
  })
  const last = decisions.at(-1)
  const revisions = decisions.filter((decision) => decision === 'revise').length
  const summary = last === 'pass'
    ? revisions ? `Provenance asked for ${count(revisions, 'revision')}, then passed the reply.` : 'Provenance passed the reply.'
    : last === 'reject' ? 'Provenance blocked the reply.'
      : last === 'revise' ? 'Provenance still wanted changes after the last revision, so the reply was blocked.'
        : 'Provenance did not finish its review.'
  return { summary, steps }
}

const CURATION_REVIEW_DECISIONS: Record<string, string> = {
  allow: 'allowed it.',
  revise: 'sent it back to Sculptor for changes.',
  reject: 'rejected it.',
}

function curationReviewStory(runs: AgentExchange[]): Story {
  const steps = runs.map((run) => {
    if (run.status !== 'success') return failedStep(run)
    const review = fields(run.output)
    const decision = text(review.decision) ?? ''
    const findings = items<Finding>(review.findings).map((finding) => finish(quote(finding.explanation, 260)))
    return `Provenance checked Sculptor's proposal against the saved memories it cites and ${CURATION_REVIEW_DECISIONS[decision] ?? `decided “${formatMachineLabel(decision)}”.`}${findings.length ? ` ${findings.join(' ')}` : ''}`
  })
  const decision = text(fields(runs.at(-1)?.output).decision)
  return {
    summary: decision === 'allow' ? 'Provenance allowed the memory change.'
      : decision ? 'Provenance did not allow the memory change as proposed.' : 'Provenance did not finish its review.',
    steps,
  }
}

// ---------------------------------------------------------------------- Muse

const BOOK_NEEDS: Record<string, string> = {
  yes: 'needs text from the book',
  no: "doesn't need text from the book",
  unsure: 'might need text from the book',
}

const MEMORY_NEEDS: Record<string, string> = {
  own_earlier_reflections: 'asks about things you told Linger before',
  named_sources: 'names outside sources to look up',
  source_comparison: 'asks to compare sources',
  outside_recommendation: 'asks for a recommendation beyond the book',
  none: "doesn't need your memories or outside sources",
  unsure: 'might need your memories or outside sources',
}

const CITATION_NOUNS: Record<string, string> = {
  book_corpus: 'book passage',
  memory: 'memory',
  web: 'web page',
  session_line: 'earlier chat line',
}

const KEEP_REASONS: Record<string, string> = {
  durable_reflection: 'a lasting reflection',
  stable_preference_or_intention: 'a lasting habit, preference or plan',
  personally_significant_incident: 'something that mattered to you',
}

const SKIP_REASONS: Record<string, string> = {
  transient_or_low_signal: 'nothing lasting was said',
  unsupported_third_party_claim: 'it was about someone else',
  near_duplicate_without_update: 'it is already saved',
  nomination_policy_ambiguous: 'it was unclear whether saving was allowed',
  no_user_words: 'there were none of your own words to keep',
  automatic_capture_disabled: 'memory saving is turned off',
  emotional_boundary: 'the emotional boundary applied',
}

function triageStep(run: AgentExchange): string {
  const needs = fields(run.output)
  const book = BOOK_NEEDS[text(needs.book_content) ?? ''] ?? 'may or may not need the book'
  const memory = MEMORY_NEEDS[text(needs.memory) ?? ''] ?? 'may or may not need other sources'
  const override = needs.override_attempt === 'attempted' ? " It also spotted an attempt to override Linger's instructions." : ''
  return `Muse sorted your message first: it ${book}, and it ${memory}.${override}`
}

function parsedArgs(args: unknown): Fields {
  if (typeof args !== 'string') return fields(args)
  try {
    return fields(JSON.parse(args))
  } catch {
    return {}
  }
}

function toolStep(tool: string, args: unknown): string | null {
  if (tool.startsWith('final_result')) return null
  if (tool === 'librarian_route') return 'Muse asked Librarian which book and chapter you are on.'
  if (tool === 'librarian_search') return 'Muse asked Librarian for passages from the book.'
  if (tool === 'serendipity_explore') {
    const intent = text(parsedArgs(args).intent) ?? ''
    return `Muse asked Serendipity to ${INTENTS[intent] ?? 'look for a connection'}.`
  }
  return `Muse used ${formatMachineLabel(tool)}.`
}

function citations(candidate: Fields): string {
  const counts = new Map<string, number>()
  for (const use of items(candidate.evidence_uses)) {
    const noun = CITATION_NOUNS[text(use.source_kind) ?? ''] ?? 'source'
    counts.set(noun, (counts.get(noun) ?? 0) + 1)
  }
  if (counts.size === 0) return 'with no citations'
  return `citing ${[...counts].map(([noun, n]) => count(n, noun)).join(' and ')}`
}

function nominationStep(candidate: Fields): string | null {
  const memory = fields(candidate.memory)
  if (memory.kind === 'memory_candidate') {
    return `It proposed saving ${quote(text(memory.text))} as a memory, because it is ${KEEP_REASONS[text(memory.reason_code) ?? ''] ?? 'worth keeping'}.`
  }
  if (memory.kind === 'no_memory_candidate') {
    return `It proposed nothing to remember, because ${SKIP_REASONS[text(memory.reason_code) ?? ''] ?? formatMachineLabel(text(memory.reason_code) ?? 'of its policy')}.`
  }
  return null
}

function museStory(runs: AgentExchange[], turn: TurnRecord): Story {
  const steps: string[] = []
  for (const run of runs) {
    if (run.status !== 'success') {
      steps.push(failedStep(run))
      continue
    }
    if (run.stage === 'turn_triage') {
      steps.push(triageStep(run))
      continue
    }
    if (run.stage !== 'draft' && run.stage !== 'revision') {
      steps.push(genericStep(run))
      continue
    }
    for (const step of run.steps ?? []) {
      if (step.kind !== 'tool-call' || !step.tool) continue
      const line = toolStep(step.tool, step.args)
      if (line) steps.push(line)
    }
    const candidate = fields(run.output)
    const reply = quote(text(candidate.reply), 220)
    steps.push(run.stage === 'draft'
      ? `Muse drafted a reply, ${citations(candidate)}: ${reply}`
      : `Muse rewrote the reply after Provenance's review, ${citations(candidate)}: ${reply}`)
    const nomination = run.stage === 'draft' ? nominationStep(candidate) : null
    if (nomination) steps.push(nomination)
  }
  const drafted = runs.some((run) => run.stage === 'draft')
  const revisions = runs.filter((run) => run.stage === 'revision').length
  const source = turn.inspection.release?.release_source
  const summary = !drafted ? 'Muse did not draft a reply on this turn.'
    : source === 'muse_candidate'
      ? revisions ? `Muse drafted the reply, revised it ${revisions === 1 ? 'once' : `${revisions} times`}, and it reached you.` : 'Muse drafted the reply, and it reached you.'
      : source === 'application_safe_decline' ? 'Muse drafted a reply, but it was blocked before reaching you.'
        : 'Muse drafted a reply, but Linger sent a fixed message instead.'
  return { summary, steps }
}

// ----------------------------------------------------------------- Librarian

const UNCERTAIN_REASONS: Record<string, string> = {
  insufficient_context: 'there was not enough to go on',
  conflicting_context: 'the clues conflicted',
  low_confidence: 'it was not confident enough',
}

const REQUEST_PURPOSES: Record<string, string> = {
  reference: 'find the passage you referred to',
  answer: 'answer your question',
  progress: 'check how far you have read',
}

const EVIDENCE_STRENGTH: Record<string, string> = {
  sufficient: 'strong enough to answer from',
  weak: 'too thin to rely on fully',
  none: 'no help for this question',
}

function librarianStep(run: AgentExchange, turn: TurnRecord): string {
  const out = fields(run.output)
  const resolution = turn.inspection.context_resolution
  const title = (workId: unknown) =>
    workId === resolution.work_id && resolution.work_title ? resolution.work_title : text(workId) ?? 'the book'
  switch (run.stage) {
    case 'boundary_inference':
      if (out.outcome === 'candidate') {
        const basis = out.authorization_basis === 'memory_supported' ? ', backed by what you told Linger before' : ''
        return `Librarian worked out how far you have read: ${title(out.work_id)}, up to chapter ${String(out.chapter_number)} (${sure(out.confidence)}${basis}).`
      }
      if (out.outcome === 'passages') {
        return `Librarian matched what you described to ${count(items(out.passage_evidence_ids).length, 'passage')} in ${title(out.work_id)} (${sure(out.confidence)}).`
      }
      return `Librarian could not tell how far you have read, because ${UNCERTAIN_REASONS[text(out.reason_code) ?? ''] ?? 'the context was unclear'}, so it stayed cautious about spoilers.`
    case 'event_identification':
      return out.outcome === 'identified'
        ? `Librarian recognised the scene you described: ${quote(text(out.explanation), 260)}`
        : `Librarian could not pin down the scene you described, because ${UNCERTAIN_REASONS[text(out.reason_code) ?? ''] ?? 'the context was unclear'}: ${quote(text(out.explanation), 260)}`
    case 'book_request': {
      const parts = items(out.parts)
      const purposes = [...new Set(parts.map((part) => REQUEST_PURPOSES[text(part.purpose) ?? ''] ?? 'look something up'))]
      return `Librarian planned ${count(parts.length, 'look-up')} in the book, to ${purposes.join(' and ')}.`
    }
    case 'evidence_strength': {
      const strength = EVIDENCE_STRENGTH[text(out.evidence_strength) ?? ''] ?? 'of unclear use'
      const limits = items<string>(out.limitations)
      return `Librarian judged the passages it found ${strength}: ${finish(quote(text(out.strength_reason), 260))}${limits.length ? ` Limits it noted: ${limits.join('; ')}.` : ''}`
    }
    default:
      return genericStep(run)
  }
}

function librarianStory(runs: AgentExchange[], turn: TurnRecord): Story {
  const steps = runs.map((run) => (run.status === 'success' ? librarianStep(run, turn) : failedStep(run)))
  const grounding = turn.inspection.librarian_grounding.length
  return {
    summary: grounding
      ? `Librarian fetched book passages ${count(grounding, 'time')}, staying within the chapters you have read.`
      : 'Librarian worked out what you are reading; no book passages were fetched.',
    steps,
  }
}

// ------------------------------------------------------------------ Sculptor

function curationStep(out: Fields): string {
  if (out.kind === 'no_curation_proposal') {
    return `Sculptor looked over your saved memories and proposed no change: ${quote(text(out.reason), 260)}`
  }
  const action = fields(out.action)
  const sources = items(action.source_memory_ids).length
  switch (action.action) {
    case 'link_duplicates':
      return `Sculptor proposed marking ${count(sources, 'saved memory')} as saying the same thing.`
    case 'update_derived_summary':
      return `Sculptor proposed a summary of ${count(sources, 'saved memory')}: ${quote(text(action.summary), 260)}`
    case 'assign_topic_group':
      return `Sculptor proposed grouping ${count(sources, 'saved memory')} under the topic ${quote(text(action.topic_label))}.`
    case 'tombstone_for_retrieval':
      return 'Sculptor proposed hiding one saved memory from search, because another one already says the same thing.'
    case 'restore_to_retrieval':
      return 'Sculptor proposed making a hidden memory searchable again.'
    default:
      return `Sculptor proposed ${formatMachineLabel(text(action.action) ?? 'a change')}.`
  }
}

function sculptorStory(runs: AgentExchange[]): Story {
  const steps = runs.map((run) => {
    if (run.status !== 'success') return failedStep(run)
    return run.stage === 'curation' ? curationStep(fields(run.output)) : genericStep(run)
  })
  const curation = runs.find((run) => run.stage === 'curation' && run.status === 'success')
  return {
    summary: !curation ? 'Sculptor did not propose a memory change.'
      : fields(curation.output).kind === 'no_curation_proposal' ? 'Sculptor proposed no change to your memories.'
        : 'Sculptor proposed a change to how your memories are organised for search.',
    steps,
  }
}

function storyFor(id: ComponentId, runs: AgentExchange[], turn: TurnRecord): Story | null {
  switch (id) {
    case 'preflight': return preflightStory(runs)
    case 'muse': return museStory(runs, turn)
    case 'provenance': return reviewStory(runs)
    case 'curation_review': return curationReviewStory(runs)
    case 'librarian': return librarianStory(runs, turn)
    case 'sculptor': return sculptorStory(runs)
    default: return null
  }
}

/** The plain retelling of one agent component's recorded runs, or null without any. */
export function agentStory(id: ComponentId, runs: AgentExchange[], turn: TurnRecord): Story | null {
  const story = runs.length ? storyFor(id, runs, turn) : null
  return story && { ...story, steps: story.steps.map(finish) }
}
