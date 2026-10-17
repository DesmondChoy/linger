import type { AgentName, ProgressEvent } from '../types'

/** One agent stage, paired from its `running` and terminal progress events. */
export type AgentStep = {
  key: string
  agent: AgentName
  stage: string
  status: ProgressEvent['status']
  startedMs: number
  /** Null while a stage is still running, or for stages reported only once. */
  durationMs: number | null
  from: AgentName
  to: AgentName
  detail: string
}

export type AgentTotal = {
  agent: AgentName
  /** Measured time this agent spent on its own work. */
  durationMs: number
  /** Time inside this agent's stages spent waiting on agents it called. */
  waitingMs: number
  steps: number
}

/**
 * Pair progress events into stages with durations.
 *
 * A stage that emits `running` and then a terminal event yields a measured
 * duration. Stages reported only once — Serendipity's individual searches, for
 * instance — are kept in order with a null duration rather than being given a
 * fabricated one.
 */
export function toAgentSteps(events: ProgressEvent[]): AgentStep[] {
  const steps: AgentStep[] = []
  const openByStage = new Map<string, AgentStep>()

  for (const event of events) {
    const stageKey = `${event.agent}::${event.stage}`
    if (event.status === 'running') {
      const step: AgentStep = {
        key: `${stageKey}::${event.sequence}`,
        agent: event.agent,
        stage: event.stage,
        status: 'running',
        startedMs: event.elapsed_ms,
        durationMs: null,
        from: event.input_origin,
        to: event.output_receiver,
        detail: event.detail,
      }
      openByStage.set(stageKey, step)
      steps.push(step)
      continue
    }

    const open = openByStage.get(stageKey)
    if (open) {
      open.status = event.status
      open.durationMs = Math.max(0, event.elapsed_ms - open.startedMs)
      open.detail = event.detail
      openByStage.delete(stageKey)
      continue
    }

    steps.push({
      key: `${stageKey}::${event.sequence}`,
      agent: event.agent,
      stage: event.stage,
      status: event.status,
      startedMs: event.elapsed_ms,
      durationMs: null,
      from: event.input_origin,
      to: event.output_receiver,
      detail: event.detail,
    })
  }

  return steps
}

type Interval = [number, number]

/** Total length covered by possibly overlapping intervals. */
function coveredMs(intervals: Interval[]): number {
  const sorted = [...intervals].sort((a, b) => a[0] - b[0])
  let total = 0
  let end = -Infinity
  for (const [start, stop] of sorted) {
    if (stop <= end) continue
    total += stop - Math.max(start, end)
    end = stop
  }
  return total
}

function measured(step: AgentStep): Interval | null {
  return step.durationMs === null ? null : [step.startedMs, step.startedMs + step.durationMs]
}

/**
 * Time per agent, in the order each agent first appeared.
 *
 * An agent's stage spans the stages it called, so that overlap counts as
 * waiting rather than work; otherwise Muse's draft would also claim the
 * Serendipity search it was waiting on.
 */
export function toAgentTotals(steps: AgentStep[]): AgentTotal[] {
  const agents = [...new Set(steps.map((step) => step.agent))]
  return agents.map((agent) => {
    const own = steps.filter((step) => step.agent === agent)
    const spans = own.map(measured).filter((span) => span !== null)
    const called = steps
      .filter((step) => step.from === agent && step.agent !== agent)
      .map(measured)
      .filter((span) => span !== null)
    // Clip each called stage to this agent's own stages before measuring the wait.
    const waitingMs = coveredMs(spans.flatMap(([start, stop]) => called
      .map(([from, to]): Interval => [Math.max(start, from), Math.min(stop, to)])
      .filter(([from, to]) => to > from)))
    return { agent, durationMs: coveredMs(spans) - waitingMs, waitingMs, steps: own.length }
  })
}

export function formatSeconds(milliseconds: number): string {
  return `${(milliseconds / 1000).toFixed(1)}s`
}
