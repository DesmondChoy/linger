import type { RiskCode, TurnRecord } from '../../types'
import { FINDING_EXPLANATIONS } from '../findingExplanations'
import { formatMachineLabel } from '../formatMachineLabel'

/**
 * Serendipity's recorded search events, retold for a reader: what it was asked
 * to find, where it looked, what it picked, and whether the reply built on it
 * reached them. Developer inspect only; the raw events stay below it.
 */

type Evidence = { evidence_id: string; excerpt?: string; source_kind?: string }
type ConnectionEvent = {
  kind: string
  status: string
  source?: string
  operation?: string
  query?: string
  evidence?: Evidence[]
  decision?: Record<string, unknown>
  release_source?: string
  provenance_verdicts?: string[]
  released_evidence_ids?: string[]
  retrieved_work_ids?: string[]
}

/** A one-line outcome, then what happened in order. */
export type Story = { summary: string; steps: string[] }

export const INTENTS: Record<string, string> = {
  recall_memory: 'find something you told Linger before that relates to your message',
  find_connection: 'find a connection between your message and your reading or earlier reflections',
  gather_sources: 'gather public sources about your question',
  get_recommendation: 'recommend something beyond the book',
}

const SOURCES: Record<string, string> = {
  memory: 'your saved memories',
  book_corpus: 'the books you have confirmed reading',
  web: 'the public web',
}

const DECLINE_REASONS: Record<string, string> = {
  no_permitted_evidence: 'there was nothing it was allowed to search',
  insufficient_evidence: 'what it found was too thin to support a link',
  unsupported_cue: 'your message did not give it enough to look for',
  generic_theme_match: 'the only matches were loose, generic themes',
  no_matching_memory: 'none of your saved memories matched',
  no_clear_winner: 'no candidate was clearly better than the others',
  spoiler_boundary: 'the link would have revealed parts of the book you have not reached',
  source_scope_violation: 'the link needed a source it was not allowed to use',
  unsafe_evidence: 'the evidence was not safe to use',
  retrieval_unavailable: 'the sources could not be searched',
}

export function quote(text: string | undefined, max = 140): string {
  const flat = text?.replace(/\s+/g, ' ').trim()
  if (!flat) return 'an unrecorded item'
  const trimmed = flat.length > max ? `${flat.slice(0, max - 1).trimEnd()}…` : flat
  return `“${trimmed}”`
}

/** End a step with a full stop unless it already ends a sentence, quoted or not. */
export function finish(step: string): string {
  return /[.!?…]”?$/.test(step) ? step : `${step}.`
}

export function plural(noun: string, n: number): string {
  if (n === 1) return noun
  return /[^aeiou]y$/.test(noun) ? `${noun.slice(0, -1)}ies` : `${noun}s`
}

export function count(n: number, noun: string): string {
  return `${n} ${plural(noun, n)}`
}

function sourceName(source: string | undefined): string {
  return SOURCES[source ?? ''] ?? formatMachineLabel(source ?? 'a source')
}

/** A fetched page's title, from the "Title: …" line its excerpt starts with. */
function pageTitle(excerpt: string | undefined): string {
  const title = excerpt?.match(/^Title:\s*(.+)$/m)?.[1]
  return quote(title ?? excerpt, 90)
}

/** What the first Serendipity run was asked, read from its recorded input. */
function askedStep(turn: TurnRecord): string | null {
  const run = turn.inspection.dev_trace?.agent_exchanges.find((exchange) => exchange.role === 'Serendipity')
  if (!run) return null
  let input: { intent?: string; scope?: { allowed_sources?: string[] } }
  try {
    input = JSON.parse(run.input_prompt)
  } catch {
    return null
  }
  const goal = INTENTS[input.intent ?? ''] ?? formatMachineLabel(input.intent ?? 'look for a connection')
  const sources = (input.scope?.allowed_sources ?? []).map(sourceName)
  const where = sources.length ? ` It was allowed to look only in ${sources.join(' and ')}.` : ''
  return `Linger asked Serendipity to ${goal}.${where}`
}

function webStep(event: ConnectionEvent, seen: Set<string>): string {
  const evidence = event.evidence ?? []
  evidence.forEach((item) => seen.add(item.evidence_id))
  if (event.operation === 'get_page') {
    if (event.status === 'retrieval_unavailable') return 'A page could not be opened.'
    if (evidence.length === 0) return 'Opened a page, but it had nothing usable.'
    return `Read the page ${evidence.map((item) => pageTitle(item.excerpt)).join('; ')}`
  }
  if (event.status === 'retrieval_unavailable') return 'The web search could not run.'
  if (event.status === 'no_evidence') return 'The web search found nothing relevant.'
  if (evidence.length === 0) return 'The web search returned pages worth opening.'
  return `The web search returned ${count(evidence.length, 'page')}: ${evidence.map((item) => pageTitle(item.excerpt)).join('; ')}`
}

function queryStep(event: ConnectionEvent): string | null {
  if (event.status === 'blocked') return 'A web search was blocked because it would have sent your private details.'
  // An opened page is told by its result; only a search's wording is worth showing.
  return event.operation === 'get_page' ? null : `Searched the web for ${quote(event.query)}`
}

function searchStep(event: ConnectionEvent, position: number, seen: Set<string>): string {
  const noun = event.source === 'memory' ? 'memory' : 'passage'
  const label = `Search ${position} of ${sourceName(event.source)}`
  if (event.status === 'no_evidence') return `${label} found nothing relevant.`
  if (event.status === 'retrieval_unavailable') return `${label} could not run.`
  const evidence = event.evidence ?? []
  const fresh = evidence.filter((item) => !seen.has(item.evidence_id))
  fresh.forEach((item) => seen.add(item.evidence_id))
  if (evidence.length === 0) return `${label} finished (${formatMachineLabel(event.status)}).`
  if (fresh.length === 0) return `${label} found the same ${plural(noun, evidence.length)} again.`
  const again = evidence.length - fresh.length
  return `${label} found ${fresh.length} new ${plural(noun, fresh.length)}: ${fresh.map((item) => quote(item.excerpt)).join('; ')}${again ? ` (plus ${again} already found)` : ''}`
}

type Candidate = { candidate_id: string; tentative_claim: string; evidence_ids: string[] }

/** The evidence Serendipity handed on: the chosen candidate's, or the recalled or gathered items. */
function pickedIds(event: ConnectionEvent): string[] {
  const decision = event.decision ?? {}
  if (event.status === 'proposal') {
    const shortlist = (decision.shortlist as Candidate[] | undefined) ?? []
    return shortlist.find((item) => item.candidate_id === decision.selected_candidate_id)?.evidence_ids ?? []
  }
  return (decision.evidence_ids as string[] | undefined) ?? []
}

function decisionStep(event: ConnectionEvent, excerpts: Map<string, string | undefined>): string {
  const decision = event.decision ?? {}
  const found = new Set((event.evidence ?? []).map((item) => item.evidence_id)).size
  if (event.status === 'failed') return 'Serendipity failed partway, so it offered no connection.'
  if (event.status === 'decline') {
    const reason = DECLINE_REASONS[String(decision.reason)] ?? formatMachineLabel(String(decision.reason ?? 'unknown'))
    return `Serendipity decided not to offer anything, because ${reason}.`
  }
  if (event.status === 'recall' || event.status === 'gathered') {
    const picked = pickedIds(event)
    const what = picked.map((id) => quote(excerpts.get(id))).join('; ')
    const ofFound = found > picked.length ? ` of the ${found} it found` : ''
    const note = typeof decision.relevance_note === 'string' ? ` Its own note: “${decision.relevance_note}”` : ''
    return `Serendipity picked ${picked.length}${ofFound}: ${finish(what)}${note}`
  }
  if (event.status === 'proposal') {
    const shortlist = (decision.shortlist as Candidate[] | undefined) ?? []
    const chosen = shortlist.find((item) => item.candidate_id === decision.selected_candidate_id)
    const certainty = typeof decision.uncertainty === 'string' ? ` with ${decision.uncertainty} uncertainty` : ''
    return `Serendipity compared ${count(shortlist.length, 'possible link')} and proposed one${certainty}: ${quote(chosen?.tentative_claim, 220)}`
  }
  return `Serendipity finished with “${formatMachineLabel(event.status)}”.`
}

function releaseStep(event: ConnectionEvent, turn: TurnRecord, picked: string[]): string {
  const findings = turn.inspection.release?.finding_codes ?? []
  const why = findings.length
    ? ` ${findings.map((code) => FINDING_EXPLANATIONS[code as RiskCode] ?? `Provenance flagged ${formatMachineLabel(code)}.`).join(' ')}`
    : ''
  switch (event.release_source) {
    case 'muse_candidate': {
      if (picked.length === 0) return 'Muse replied without anything from Serendipity, and that reply reached you.'
      const used = picked.filter((id) => event.released_evidence_ids?.includes(id)).length
      return used
        ? 'Muse wrote the reply around it, Provenance checked it, and you saw that reply.'
        : 'Muse wrote the reply and Provenance passed it, but the reply did not cite what Serendipity picked.'
    }
    case 'application_safe_decline':
      return (event.provenance_verdicts ?? []).includes('reject')
        ? `Muse wrote a reply using it, but Provenance rejected that reply, so Linger sent a fixed decline message instead.${why} Open Provenance for its full review.`
        : `The reply could not be released, so Linger sent a fixed decline message instead.${why}`
    case 'application_clarification':
      return 'Linger asked you a clarifying question instead of using it.'
    case 'application_emotional_boundary':
    case 'application_language_boundary':
      return 'A safety boundary applied, so Linger sent a fixed boundary message instead.'
    default:
      return `The turn ended with ${formatMachineLabel(event.release_source ?? event.status)}.`
  }
}

function summaryFor(discovery: ConnectionEvent | undefined, release: ConnectionEvent | undefined): string {
  const found = discovery && ['recall', 'gathered', 'proposal'].includes(discovery.status)
  if (!discovery) return 'Serendipity searched but recorded no decision.'
  if (!found) return 'Serendipity offered nothing.'
  if (release?.release_source === 'muse_candidate') return 'Serendipity found something, and the reply built on it reached you.'
  if ((release?.provenance_verdicts ?? []).includes('reject')) return 'Serendipity found something, but Provenance blocked the reply built on it.'
  return 'Serendipity found something, but the reply built on it did not reach you.'
}

export function connectionStory(turn: TurnRecord): Story | null {
  const events = (turn.inspection.dev_trace?.connection_events ?? []) as ConnectionEvent[]
  // Every turn records its release; only the other events show Serendipity ran.
  if (!events.some((event) => event.kind !== 'release')) return null
  const steps: string[] = []
  const asked = askedStep(turn)
  if (asked) steps.push(asked)

  const seen = new Set<string>()
  const excerpts = new Map<string, string | undefined>()
  const searches = new Map<string, number>()
  let picked: string[] = []
  let discovery: ConnectionEvent | undefined
  let release: ConnectionEvent | undefined
  for (const event of events) {
    for (const item of event.evidence ?? []) excerpts.set(item.evidence_id, item.excerpt)
    if (event.kind === 'search' && event.source === 'web') {
      steps.push(webStep(event, seen))
    } else if (event.kind === 'search') {
      const position = (searches.get(event.source ?? '') ?? 0) + 1
      searches.set(event.source ?? '', position)
      steps.push(searchStep(event, position, seen))
    } else if (event.kind === 'query') {
      const step = queryStep(event)
      if (step) steps.push(step)
    } else if (event.kind === 'book_retrieval' && event.status === 'ok') {
      steps.push(`Searched a book you have read and got ${count(event.retrieved_work_ids?.length ?? 0, 'passage')} back.`)
    } else if (event.kind === 'discovery') {
      discovery = event
      picked = pickedIds(event)
      steps.push(decisionStep(event, excerpts))
    } else if (event.kind === 'release') {
      release = event
      steps.push(releaseStep(event, turn, picked))
    }
  }
  return { summary: summaryFor(discovery, release), steps: steps.map(finish) }
}

function isWeb(event: ConnectionEvent): boolean {
  return event.source === 'web' && (event.kind === 'query' || event.kind === 'search')
}

/** The public web's part of the turn: what was searched, what was read, and what the reply cited. */
export function webStory(turn: TurnRecord): Story | null {
  const events = (turn.inspection.dev_trace?.connection_events ?? []) as ConnectionEvent[]
  const web = events.filter(isWeb)
  if (web.length === 0) return null
  const seen = new Set<string>()
  const steps = web
    .map((event) => (event.kind === 'query' ? queryStep(event) : webStep(event, seen)))
    .filter((step): step is string => step !== null)

  const titles = new Map<string, string>()
  for (const event of web) for (const item of event.evidence ?? []) titles.set(item.evidence_id, pageTitle(item.excerpt))
  const release = events.find((event) => event.kind === 'release')
  const cited = release?.release_source === 'muse_candidate'
    ? (release.released_evidence_ids ?? []).filter((id) => titles.has(id))
    : []
  if (release && release.release_source !== 'muse_candidate') steps.push('The reply built on these pages did not reach you.')
  else if (cited.length) steps.push(`The reply that reached you cited ${cited.map((id) => titles.get(id)).join('; ')}`)
  else if (release) steps.push('The reply that reached you cited none of these pages.')

  const searches = web.filter((event) => event.kind === 'query' && event.status === 'sent' && event.operation !== 'get_page').length
  const pages = web.filter((event) => event.kind === 'search' && event.operation === 'get_page' && event.evidence?.length).length
  const blocked = web.some((event) => event.status === 'blocked') ? ' One search was blocked for privacy.' : ''
  return {
    summary: `Serendipity searched the web ${searches === 1 ? 'once' : `${searches} times`} and read ${count(pages, 'page')}; the reply cited ${cited.length}.${blocked}`,
    steps: steps.map(finish),
  }
}
