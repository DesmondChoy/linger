import { describe, expect, it } from 'vitest'
import { layoutScene } from './layout'
import { components, objectiveScenes } from './scenarios'
import type { GraphNode, Scene } from './types'

const scenes = objectiveScenes.flatMap(objective => objective.scenes)

function example(id: string): Scene {
  const scene = scenes.find(item => item.id === id)
  if (!scene) throw new Error(`Missing layout example: ${id}`)
  return scene
}

function visualTop(node: GraphNode) {
  const kind = components[node.id].kind
  return node.y - (kind === 'agent' && node.id !== 'preflight' ? 80 : 25)
}

function visualBottom(node: GraphNode) {
  return node.y + (components[node.id].kind === 'service' || node.id === 'preflight' ? 69 : 88)
}

describe('Structured Studio layouts', () => {
  for (const scene of scenes) {
    it(`${scene.id} preserves semantic data and contains every card in one region`, () => {
      const before = JSON.stringify(scene)
      const layout = layoutScene(scene)
      expect(JSON.stringify(scene)).toBe(before)
      expect(layout.nodes.map(({ x: _x, y: _y, ...rest }) => rest))
        .toEqual(scene.nodes.map(({ x: _x, y: _y, ...rest }) => rest))
      expect(layout.width).toBe(1400)
      expect(layout.height).toBeGreaterThanOrEqual(290)
      expect(layout.height).toBeLessThanOrEqual(700)

      for (const node of layout.nodes) {
        const regions = layout.groups.filter(group => (
          node.x - 92 >= group.x && node.x + 92 <= group.x + group.width
          && node.y - 80 >= group.y && visualBottom(node) <= group.y + group.height
        ))
        expect(regions.length, `${node.id} enclosing region`).toBe(1)
        expect(visualTop(node), `${node.id} below group heading`).toBeGreaterThanOrEqual(regions[0].y + 40)
      }
      for (const [index, group] of layout.groups.entries()) {
        expect(group.y + group.height).toBeLessThanOrEqual(layout.height)
        for (const other of layout.groups.slice(index + 1)) {
          const overlap = group.x < other.x + other.width && group.x + group.width > other.x
            && group.y < other.y + other.height && group.y + group.height > other.y
          expect(overlap, `${group.id} overlaps ${other.id}`).toBe(false)
        }
      }
    })
  }

  it('crops simple conversations and offline curation to one compact band', () => {
    for (const id of ['personal-reflection', 'answerable-reflection', 'distress-boundary', 'bounded-proposal', 'no-curation']) {
      const layout = layoutScene(example(id))
      expect(layout.height).toBe(290)
      expect(layout.groups).toHaveLength(1)
      expect(new Set(layout.nodes.map(node => node.y)).size).toBe(1)
    }
    expect(layoutScene(example('bounded-proposal')).groups[0].label).toContain('proposals only')
  })

  it('keeps retrieval and current conversation in distinct regions', () => {
    expect(layoutScene(example('relevant-history')).groups.map(group => group.label))
      .toEqual(['Memory retrieval', 'Current conversation'])
    expect(layoutScene(example('passage-needed')).groups.map(group => group.label))
      .toEqual(['Evidence retrieval', 'Current conversation'])
  })

  it('preserves vertical Muse/Librarian alignment where the scenario supplies it', () => {
    for (const id of ['passage-needed', 'relevant-history', 'infer-safe-ceiling']) {
      const nodes = layoutScene(example(id)).nodes
      expect(nodes.find(node => node.id === 'muse')?.x).toBe(nodes.find(node => node.id === 'librarian')?.x)
    }
  })

  it('keeps session state below the compact main conversation', () => {
    for (const id of ['relevant-history', 'irrelevant-history', 'follow-correction', 'fresh-session']) {
      const layout = layoutScene(example(id))
      const session = layout.nodes.find(node => node.id === 'session')
      const muse = layout.nodes.find(node => node.id === 'muse')
      expect(session?.x).toBe(320)
      expect(session && muse && session.y > muse.y).toBe(true)
      expect(layout.height).toBe(layout.nodes.some(node => node.id === 'librarian') ? 644 : 430)
    }
  })
})

describe('Compact live layout', () => {
  const spine: GraphNode['id'][] = ['input', 'preflight', 'muse', 'provenance', 'release', 'response']
  const specialists: GraphNode['id'][] = ['librarian', 'corpus', 'serendipity', 'web', 'memory', 'sculptor', 'curation_review']

  function compactScene(ids: GraphNode['id'][]): Scene {
    return {
      ...example('passage-needed'),
      nodes: ids.map(id => ({ id, x: 0, y: 0 })),
      edges: [],
      layout: 'compact',
    }
  }

  it('gives every card its own space inside one region, whatever ran', () => {
    for (const extra of [[], ['librarian'], specialists] as GraphNode['id'][][]) {
      const layout = layoutScene(compactScene([...spine, ...extra]))
      for (const [index, node] of layout.nodes.entries()) {
        const regions = layout.groups.filter(group => (
          node.x - 92 >= group.x && node.x + 92 <= group.x + group.width
          && node.y - 80 >= group.y && visualBottom(node) <= group.y + group.height
        ))
        expect(regions.length, `${node.id} enclosing region`).toBe(1)
        for (const other of layout.nodes.slice(index + 1)) {
          const overlap = Math.abs(node.x - other.x) < 184 && Math.abs(node.y - other.y) < 180
          expect(overlap, `${node.id} overlaps ${other.id}`).toBe(false)
        }
      }
    }
  })

  it('keeps Librarian above Muse and names the specialists it shows', () => {
    const layout = layoutScene(compactScene([...spine, 'librarian']))
    const at = (id: GraphNode['id']) => layout.nodes.find(node => node.id === id)!
    expect(at('librarian').x).toBe(at('muse').x)
    expect(at('librarian').y).toBeLessThan(at('muse').y)
    expect(layout.groups.map(group => group.label)).toEqual(['Book evidence', 'Current conversation'])
    expect(layoutScene(compactScene([...spine, 'serendipity', 'memory'])).groups[0].label)
      .toBe('Connections · Memory')
  })

  it('puts memory capture in its own band directly below Provenance', () => {
    const layout = layoutScene(compactScene([...spine, 'memory_policy']))
    const at = (id: GraphNode['id']) => layout.nodes.find(node => node.id === id)!
    expect(at('memory_policy').x).toBe(at('provenance').x)
    expect(at('memory_policy').y).toBeGreaterThan(at('provenance').y)
    expect(layout.groups.map(group => group.id)).toEqual(['conversation', 'memory-capture'])
    expect(layout.height).toBeGreaterThanOrEqual(layout.groups[1].y + layout.groups[1].height)
  })

  it('omits the conversation band for an offline task with no spine', () => {
    const layout = layoutScene(compactScene(['sculptor', 'curation_review']))
    expect(layout.groups.map(group => group.id)).toEqual(['specialists'])
    for (const node of layout.nodes) expect(visualBottom(node)).toBeLessThanOrEqual(layout.height)
  })

  it('draws only the conversation when no specialist ran', () => {
    const layout = layoutScene(compactScene(spine))
    expect(layout.groups.map(group => group.id)).toEqual(['conversation'])
  })
})
