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
  /** Summed duration of this agent's measured stages. */
  durationMs: number
  steps: number
  /** True when some of this agent's stages reported no measurable duration. */
  partial: boolean
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

/** Total measured time per agent, in the order each agent first appeared. */
export function toAgentTotals(steps: AgentStep[]): AgentTotal[] {
  const totals = new Map<AgentName, AgentTotal>()
  for (const step of steps) {
    const existing = totals.get(step.agent) ?? {
      agent: step.agent,
      durationMs: 0,
      steps: 0,
      partial: false,
    }
    existing.steps += 1
    if (step.durationMs === null) existing.partial = true
    else existing.durationMs += step.durationMs
    totals.set(step.agent, existing)
  }
  return [...totals.values()]
}

export function formatSeconds(milliseconds: number): string {
  return `${(milliseconds / 1000).toFixed(1)}s`
}
