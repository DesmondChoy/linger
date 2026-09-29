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

// Compact layout: three columns, the conversation snaking over two rows, and
// specialists stacked above in fixed slots so no two cards can share a place.
const COMPACT_WIDTH = 860
const COMPACT_COLUMNS = [150, 430, 710]
const COMPACT_ROW_PITCH = 205
const COMPACT_TOP = 118
const COMPACT_BOTTOM = 96
const COMPACT_CONVERSATION: Partial<Record<ComponentId, [row: number, column: number]>> = {
  input: [0, 0], preflight: [0, 1], muse: [0, 2],
  response: [1, 0], release: [1, 1], provenance: [1, 2],
}
// Row 0 sits just above the conversation; Librarian stays directly above Muse.
const COMPACT_SPECIALISTS: Partial<Record<ComponentId, [row: number, column: number]>> = {
  librarian: [0, 2], serendipity: [0, 1], sculptor: [0, 0],
  corpus: [1, 2], web: [1, 1], memory: [1, 0], curation_review: [1, 0],
}
// After release, below Provenance: where a reviewed memory is saved or refused.
const COMPACT_AFTER_RELEASE = new Set<ComponentId>(['memory_policy'])
const SPECIALIST_GROUPS: [label: string, ids: ComponentId[]][] = [
  ['Book evidence', ['librarian', 'corpus']],
  ['Connections', ['serendipity', 'web']],
  ['Memory', ['memory', 'memory_policy', 'sculptor', 'curation_review', 'capture_review', 'session', 'proposal']],
]

function placeSpecialists(nodes: GraphNode[]): Map<ComponentId, [number, number]> {
  const taken = new Set<string>()
  const placed = new Map<ComponentId, [number, number]>()
  const free = (row: number, column: number) => !taken.has(`${row}:${column}`)
  for (const node of nodes) {
    const [preferredRow, preferredColumn] = COMPACT_SPECIALISTS[node.id] ?? [0, 0]
    let slot: [number, number] | undefined = free(preferredRow, preferredColumn) ? [preferredRow, preferredColumn] : undefined
    for (let row = preferredRow; !slot; row++) {
      const column = [0, 1, 2].find(candidate => free(row, candidate))
      if (column !== undefined) slot = [row, column]
    }
    taken.add(`${slot[0]}:${slot[1]}`)
    placed.set(node.id, slot)
  }
  return placed
}

function layoutCompact(scene: Scene): SceneLayout {
  const specialists = scene.nodes.filter(node => !(node.id in COMPACT_CONVERSATION) && !COMPACT_AFTER_RELEASE.has(node.id))
  const afterRelease = scene.nodes.some(node => COMPACT_AFTER_RELEASE.has(node.id))
  const slots = placeSpecialists(specialists)
  // Draw only the specialist rows in use, highest row at the top.
  const usedRows = [...new Set([...slots.values()].map(([row]) => row))].sort((a, b) => b - a)
  const specialistHeight = usedRows.length
    ? COMPACT_TOP + (usedRows.length - 1) * COMPACT_ROW_PITCH + COMPACT_BOTTOM
    : 0
  const hasConversation = scene.nodes.some(node => node.id in COMPACT_CONVERSATION)
  const conversationY = usedRows.length ? 8 + specialistHeight + 16 : 8
  const conversationHeight = hasConversation ? COMPACT_TOP + COMPACT_ROW_PITCH + COMPACT_BOTTOM : 0
  const afterReleaseY = conversationY + conversationHeight + 16
  const afterReleaseHeight = COMPACT_TOP + COMPACT_BOTTOM
  const present = new Set(specialists.map(node => node.id))
  const specialistLabel = SPECIALIST_GROUPS
    .filter(([, ids]) => ids.some(id => present.has(id)))
    .map(([label]) => label)
    .join(' · ')
  const groups: LayoutGroup[] = [
    ...(usedRows.length
      ? [{ id: 'specialists', label: specialistLabel, x: 8, y: 8, width: COMPACT_WIDTH - 16, height: specialistHeight }]
      : []),
    ...(hasConversation
      ? [{ id: 'conversation', label: 'Current conversation', x: 8, y: conversationY, width: COMPACT_WIDTH - 16, height: conversationHeight }]
      : []),
    ...(afterRelease
      ? [{ id: 'memory-capture', label: 'Memory capture', x: 8, y: afterReleaseY, width: COMPACT_WIDTH - 16, height: afterReleaseHeight }]
      : []),
  ]
  return {
    nodes: scene.nodes.map(node => {
      if (COMPACT_AFTER_RELEASE.has(node.id)) {
        return { ...node, x: COMPACT_COLUMNS[2], y: afterReleaseY + COMPACT_TOP }
      }
      const spine = COMPACT_CONVERSATION[node.id]
      if (spine) {
        return { ...node, x: COMPACT_COLUMNS[spine[1]], y: conversationY + COMPACT_TOP + spine[0] * COMPACT_ROW_PITCH }
      }
      const [row, column] = slots.get(node.id) ?? [0, 0]
      return { ...node, x: COMPACT_COLUMNS[column], y: 8 + COMPACT_TOP + usedRows.indexOf(row) * COMPACT_ROW_PITCH }
    }),
    groups,
    width: COMPACT_WIDTH,
    height: afterRelease ? afterReleaseY + afterReleaseHeight + 8
      : hasConversation ? conversationY + conversationHeight + 8
        : Math.max(8 + specialistHeight + 8, 120),
  }
}

export function layoutScene(scene: Scene): SceneLayout {
  if (scene.layout === 'compact') return layoutCompact(scene)
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
