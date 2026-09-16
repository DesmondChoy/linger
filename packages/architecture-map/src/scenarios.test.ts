import { describe, expect, it } from 'vitest'
import catalog from './catalog.json'
import { components, objectiveScenes } from './scenarios'
import type { ComponentId } from './types'

function scene(objectiveId: string, sceneId: string) {
  const result = objectiveScenes.find((objective) => objective.objectiveId === objectiveId)
    ?.scenes.find((item) => item.id === sceneId)
  if (!result) throw new Error(`Unknown explorer Scene: ${objectiveId}/${sceneId}`)
  return result
}

function nodeIds(objectiveId: string, sceneId: string): ComponentId[] {
  return scene(objectiveId, sceneId).nodes.map((node) => node.id)
}

describe('catalog and walkthrough coverage', () => {
  it('provides multiple illustrative Scenes for every maintained Objective', () => {
    expect(objectiveScenes.map((objective) => objective.objectiveId).sort())
      .toEqual(catalog.objectives.map((objective) => objective.id).sort())
    expect(new Set(objectiveScenes.map((objective) => objective.objectiveId)).size).toBe(objectiveScenes.length)
    for (const objective of objectiveScenes) {
      expect(objective.scenes.length).toBeGreaterThanOrEqual(2)
      expect(new Set(objective.scenes.map((item) => item.id)).size).toBe(objective.scenes.length)
      for (const item of objective.scenes) {
        expect(item.input.title).toMatch(/illustrative/i)
        expect(item.statusNote.length).toBeGreaterThan(0)
      }
    }
  })

  for (const objective of objectiveScenes) {
    for (const item of objective.scenes) {
      it(`${objective.objectiveId}/${item.id} has selectable, fully explained graph elements`, () => {
        const nodes = new Set(item.nodes.map((node) => node.id))
        const edges = new Set(item.edges.map((edge) => edge.id))
        expect(nodes.size).toBe(item.nodes.length)
        expect(edges.size).toBe(item.edges.length)
        for (const node of item.nodes) {
          expect(components[node.id].id).toBe(node.id)
          expect(node.x).toBeGreaterThanOrEqual(80)
          expect(node.x).toBeLessThanOrEqual(1110)
          expect(node.y).toBeGreaterThanOrEqual(100)
          expect(node.y).toBeLessThanOrEqual(550)
        }
        for (const edge of item.edges) {
          expect(nodes.has(edge.source), `${edge.id} source`).toBe(true)
          expect(nodes.has(edge.target), `${edge.id} target`).toBe(true)
          expect(item.steps.some((step) => step.edges.includes(edge.id)), `${edge.id} walkthrough`).toBe(true)
        }
        for (const step of item.steps) {
          expect(step.nodes.length).toBeGreaterThan(0)
          for (const id of step.nodes) expect(nodes.has(id), `step node ${id}`).toBe(true)
          for (const id of step.edges) {
            expect(edges.has(id), `step edge ${id}`).toBe(true)
            const edge = item.edges.find((candidate) => candidate.id === id)
            expect(edge && step.nodes.includes(edge.source), `${id} active source`).toBe(true)
            expect(edge && step.nodes.includes(edge.target), `${id} active target`).toBe(true)
          }
        }
      })
    }
  }
})

describe('routes and authority boundaries', () => {
  it('removes retrieval from the personal book-reflection comparison', () => {
    const grounded = scene('grounded_book_reflection', 'passage-needed')
    const personal = nodeIds('grounded_book_reflection', 'personal-reflection')
    const muse = grounded.nodes.find((node) => node.id === 'muse')
    const librarian = grounded.nodes.find((node) => node.id === 'librarian')
    expect(librarian?.x).toBe(muse?.x)
    expect(librarian && muse && librarian.y < muse.y).toBe(true)
    expect(grounded.edges.find((edge) => edge.id === 'muse-librarian')?.bidirectional).toBe(true)
    expect(personal).not.toContain('librarian')
    expect(personal).not.toContain('corpus')
  })

  it('shows the preflight boundary without Muse, evidence, nomination, or candidate review', () => {
    const boundary = scene('sensitive_inference_and_capture_veto', 'distress-boundary')
    expect(boundary.nodes.map((node) => node.id)).toEqual(['input', 'preflight', 'release', 'response'])
    expect(boundary.edges.map((edge) => `${edge.source}:${edge.target}`))
      .toEqual(['input:preflight', 'preflight:release', 'release:response'])
  })

  it('keeps candidate review and deterministic release on every Muse response route', () => {
    for (const objective of objectiveScenes) {
      for (const item of objective.scenes.filter((entry) => entry.nodes.some((node) => node.id === 'muse'))) {
        expect(item.edges.some((edge) => edge.source === 'muse' && edge.target === 'provenance')).toBe(true)
        expect(item.edges.some((edge) => edge.source === 'provenance' && edge.target === 'release')).toBe(true)
        expect(item.edges.filter((edge) => edge.target === 'response').map((edge) => edge.source)).toEqual(['release'])
      }
    }
  })

  it('permits only Memory & Policy to write memory and keeps capture binding deterministic', () => {
    expect(components.capture_review.kind).toBe('service')
    expect(components.curation_review.kind).toBe('agent')
    for (const objective of objectiveScenes) {
      for (const item of objective.scenes) {
        for (const edge of item.edges.filter((candidate) => candidate.target === 'memory')) {
          expect(edge.source).toBe('memory_policy')
          expect(edge.bidirectional).not.toBe(true)
        }
      }
    }
    const capture = scene('reviewed_automatic_memory_capture', 'durable-span')
    const outputCheck = capture.steps.findIndex((step) => step.edges.includes('release-memory_policy'))
    const storage = capture.steps.findIndex((step) => step.edges.includes('memory_policy-memory'))
    const response = capture.steps.findIndex((step) => step.edges.includes('release-response'))
    expect(outputCheck).toBeGreaterThan(-1)
    expect(outputCheck).toBeLessThan(storage)
    expect(storage).toBeLessThan(response)
    expect(nodeIds('reviewed_automatic_memory_capture', 'ordinary-update')).not.toContain('memory')
    expect(nodeIds('sensitive_inference_and_capture_veto', 'sensitive-uncertainty')).not.toContain('memory')
  })

  it('ends offline curation in an observation without application or storage gates', () => {
    const curation = objectiveScenes.find((objective) => objective.objectiveId === 'bounded_memory_curation')
    expect(curation).toBeDefined()
    for (const item of curation?.scenes ?? []) {
      expect(item.status).toBe('component')
      expect(item.nodes.map((node) => node.id)).toEqual(['memory', 'sculptor', 'proposal'])
      expect(item.edges.every((edge) => edge.target !== 'memory')).toBe(true)
      expect(item.steps.at(-1)?.nodes).toContain('proposal')
    }
  })

  it('marks unsupported complete memory and cross-source flows as targets', () => {
    const targets = ['longitudinal_memory_retrieval', 'cross_source_tentative_connection', 'proactive_memory_surfacing']
    for (const objective of objectiveScenes.filter((item) => targets.includes(item.objectiveId))) {
      expect(objective.scenes.every((item) => item.status === 'target')).toBe(true)
    }
  })

  it('separates the proactive prerequisite write from later selective surfacing', () => {
    const initial = scene('proactive_memory_surfacing', 'update-and-curate')
    const later = scene('proactive_memory_surfacing', 'useful-later-cue')
    const deferred = scene('proactive_memory_surfacing', 'defer-the-same-cue')
    expect(initial.edges.some((edge) => edge.source === 'sculptor' && edge.target === 'curation_review')).toBe(true)
    expect(initial.edges.some((edge) => edge.source === 'curation_review' && edge.target === 'memory_policy')).toBe(true)
    expect(later.input).toEqual(deferred.input)
    expect(later.nodes).toEqual(deferred.nodes)
    expect(later.edges.find((edge) => edge.id === 'sculptor-muse')?.label).toBe('Surface now')
    expect(deferred.edges.find((edge) => edge.id === 'sculptor-muse')?.label).toBe('Defer')
    for (const item of [later, deferred]) {
      expect(item.nodes.map((node) => node.id)).toContain('session')
      expect(item.edges.some((edge) => edge.target === 'memory')).toBe(false)
      expect(item.edges.some((edge) => edge.source === 'librarian' && edge.target === 'sculptor')).toBe(true)
    }
  })

  it('keeps the security comparison on a legitimate grounded-book route', () => {
    const attack = scene('untrusted_content_injection_resistance', 'attack-in-evidence')
    const benign = scene('untrusted_content_injection_resistance', 'benign-evidence')
    expect(attack.input).toEqual(benign.input)
    expect(attack.nodes).toEqual(benign.nodes)
    expect(attack.nodes.map((node) => node.id)).toEqual(expect.arrayContaining(['muse', 'librarian', 'corpus', 'provenance', 'release']))
    expect(attack.statusNote).toMatch(/overlay/i)
  })
})
