import type { ComponentId, GraphNode, Scene } from './types'

interface LayoutGroup {
  id: string
  label: string
  x: number
  y: number
  width: number
  height: number
}

interface SceneLayout {
  nodes: GraphNode[]
  groups: LayoutGroup[]
  width: number
  height: number
}

const width = 1400
const conversationIds = new Set<ComponentId>([
  'input', 'preflight', 'muse', 'provenance', 'release', 'response',
])

function group(options: Pick<LayoutGroup, 'id' | 'label' | 'y' | 'height'>): LayoutGroup {
  return { ...options, x: 8, width: width - 16 }
}

function compose(options: {
  scene: Scene
  groups: LayoutGroup[]
  height: number
  position: (node: GraphNode) => Pick<GraphNode, 'x' | 'y'>
}): SceneLayout {
  return {
    nodes: options.scene.nodes.map(node => ({ ...node, ...options.position(node) })),
    groups: options.groups,
    width,
    height: options.height,
  }
}

export function layoutScene(scene: Scene): SceneLayout {
  const ids = new Set(scene.nodes.map(node => node.id))
  const scaledX = (node: GraphNode) => node.x * width / 1200
  const onConversation = (node: GraphNode) => conversationIds.has(node.id)

  if (ids.has('proposal') || scene.nodes.every(onConversation)) {
    return compose({
      scene, height: 290,
      groups: [group({ id: 'main', label: ids.has('proposal') ? 'Offline curation · proposals only' : 'Current conversation', y: 16, height: 258 })],
      position: node => ({ x: scaledX(node), y: 154 }),
    })
  }

  if (ids.has('curation_review')) {
    return compose({
      scene, height: 692,
      groups: [
        group({ id: 'conversation', label: 'Current conversation', y: 16, height: 258 }),
        group({ id: 'capture-curation', label: 'Capture and curation', y: 310, height: 366 }),
      ],
      position: node => ({
        x: scaledX(node),
        y: onConversation(node) ? 154 : node.id === 'sculptor' || node.id === 'curation_review' ? 570 : 390,
      }),
    })
  }

  if (ids.has('capture_review')) {
    return compose({
      scene, height: 610,
      groups: [
        group({ id: 'conversation', label: 'Current conversation', y: 16, height: 258 }),
        group({ id: 'capture', label: 'Reviewed memory capture', y: 310, height: 284 }),
      ],
      position: node => ({ x: scaledX(node), y: onConversation(node) ? 154 : 448 }),
    })
  }

  if (ids.has('librarian')) {
    const lowerMemorySources = scene.nodes.some(node => node.id === 'memory' && node.y > 300)
    const hasSession = ids.has('session')
    const retrievalLabel = ids.has('corpus')
      ? lowerMemorySources ? 'Evidence and memory retrieval' : 'Evidence retrieval'
      : ids.has('sculptor') ? 'Memory retrieval and surfacing' : 'Memory retrieval'

    if (lowerMemorySources) {
      return compose({
        scene, height: 694,
        groups: [
          group({ id: 'retrieval', label: retrievalLabel, y: 8, height: 400 }),
          group({ id: 'conversation', label: 'Current conversation', y: 428, height: 250 }),
        ],
        position: node => ({
          x: node.id === 'memory' ? 105 : node.id === 'memory_policy' ? 320 : scaledX(node),
          y: onConversation(node) ? 558 : node.id === 'memory' || node.id === 'memory_policy' ? 300 : 140,
        }),
      })
    }

    return compose({
      scene, height: hasSession ? 644 : 610,
      groups: [
        group({ id: 'retrieval', label: retrievalLabel, y: hasSession ? 8 : 16, height: hasSession ? 246 : 258 }),
        group({ id: 'conversation', label: 'Current conversation', y: hasSession ? 272 : 310, height: hasSession ? 356 : 284 }),
      ],
      position: node => ({
        x: node.id === 'session' ? 320 : scaledX(node),
        y: node.id === 'session' ? 550 : onConversation(node) ? hasSession ? 398 : 448 : hasSession ? 138 : 154,
      }),
    })
  }

  // Working history sits below the compact conversational row.
  return compose({
    scene, height: 430,
    groups: [group({ id: 'conversation', label: 'Current conversation', y: 16, height: 398 })],
    position: node => ({ x: node.id === 'session' ? 320 : scaledX(node), y: onConversation(node) ? 154 : 336 }),
  })
}
