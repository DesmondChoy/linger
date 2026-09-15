import { describe, expect, it } from 'vitest'
import { playableScenarios } from '@linger/architecture-map'
import type { EvaluationRun, EvaluationRunScene, EvaluationScene } from '@linger/architecture-map'
import { buildEvaluationView, failureProse } from './evaluationScene'

/**
 * These run against the committed snapshot, so they also guard the exporter:
 * if a projection drops a field the map needs, the map stops explaining the run
 * and these fail.
 */

const pigeon = playableScenarios.find((item) => item.id.startsWith('alice-pigeon'))

function runByLabel(label: string): EvaluationRun {
  const run = pigeon?.runs.find((item) => item.label === label)
  if (!run) throw new Error(`No recorded run labelled ${label}`)
  return run
}

function firstScene(run: EvaluationRun): { runScene: EvaluationRunScene; scene: EvaluationScene } {
  const runScene = run.scenes[0]
  const scene = pigeon?.scenes.find((item) => item.id === runScene.sceneId)
  if (!scene) throw new Error('The run names a scene the backstory does not define')
  return { runScene, scene }
}

describe('saved evaluation snapshot', () => {
  it('ships scenarios that carry a persona, a line and at least one run', () => {
    expect(playableScenarios.length).toBeGreaterThan(0)
    for (const scenario of playableScenarios) {
      expect(scenario.persona.context.length).toBeGreaterThan(0)
      expect(scenario.runs.length).toBeGreaterThan(0)
      for (const scene of scenario.scenes) expect(scene.line.length).toBeGreaterThan(0)
    }
  })

  it('records distinct builds rather than repeated trials of one build', () => {
    const variants = new Set(runByLabel('selection') && pigeon!.runs.map((run) => run.systemVariant))
    expect(variants.size).toBeGreaterThan(1)
  })
})

describe('buildEvaluationView', () => {
  it('draws a required-but-unreached look-up as a broken chain', () => {
    const run = runByLabel('selection')
    const { runScene, scene } = firstScene(run)
    const view = buildEvaluationView({ run, runScene, scene })

    expect(runScene.routeCalled).toBe(false)
    expect(view.retrievalMissing).toBe(true)

    const librarian = view.scene.nodes.find((node) => node.id === 'librarian')
    const corpus = view.scene.nodes.find((node) => node.id === 'corpus')
    expect(librarian?.muted).toBe(true)
    expect(corpus?.muted).toBe(true)
    expect(librarian?.footer?.tone).toBe('bad')
    expect(view.scene.summary).toContain('never made one')
  })

  it('draws a build that did retrieve as an unbroken chain', () => {
    const run = runByLabel('conditional policy')
    const { runScene, scene } = firstScene(run)
    const view = buildEvaluationView({ run, runScene, scene })

    expect(runScene.routeCalled).toBe(true)
    expect(view.retrievalMissing).toBe(false)

    const librarian = view.scene.nodes.find((node) => node.id === 'librarian')
    expect(librarian?.muted).toBe(false)
    expect(librarian?.footer?.left).toContain('chapter')
    expect(view.scene.nodes.find((node) => node.id === 'memory')?.muted).toBe(false)
    expect(view.objectives.every((objective) => objective.passed)).toBe(true)
  })

  it('never draws an edge to a component the run never involved', () => {
    for (const scenario of playableScenarios) {
      for (const run of scenario.runs) {
        for (const runScene of run.scenes) {
          const scene = scenario.scenes.find((item) => item.id === runScene.sceneId)
          if (!scene) continue
          const view = buildEvaluationView({ run, runScene, scene })
          const ids = new Set(view.scene.nodes.map((node) => node.id))
          for (const edge of view.scene.edges) {
            expect(ids.has(edge.source)).toBe(true)
            expect(ids.has(edge.target)).toBe(true)
          }
        }
      }
    }
  })

  it('grades per objective, which is the granularity the archive records', () => {
    const run = runByLabel('selection')
    const { runScene, scene } = firstScene(run)
    const view = buildEvaluationView({ run, runScene, scene })

    expect(view.objectives.length).toBe(runScene.grades.length)
    expect(view.objectives.some((objective) => !objective.passed)).toBe(true)
    // Expected outcomes are shown as what the key asked, never ticked per line.
    expect(view.expected.length).toBeGreaterThan(0)
  })

  it('renders known failure codes as prose and passes unknown ones through', () => {
    expect(failureProse('required_grounding_evidence_not_retrieved')).toContain('open the book')
    expect(failureProse('exact_quotation_missing_or_unreleased:pigeon')).toContain('quote exactly')
    expect(failureProse('some_future_code')).toBe('some future code')
  })
})
