import { useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { Icon } from './Icon'
import { components } from './scenarios'
import { layoutScene } from './layout'
import type { GraphNode, InspectorSelection, Scene, WalkthroughStep } from './types'

function ports(node: GraphNode) {
  if (components[node.id].kind === 'service' || node.id === 'preflight') return { side: 100, top: 32, bottom: 70 }
  if (components[node.id].kind === 'agent') return { side: 98, top: 88, bottom: 94 }
  return { side: 42, top: 38, bottom: 91 }
}

function connection(source: GraphNode, target: GraphNode) {
  const dx = target.x - source.x
  const dy = target.y - source.y
  const from = ports(source)
  const to = ports(target)
  if (source.id === 'memory_policy' && target.id === 'sculptor') {
    const y1 = source.y + from.bottom
    const y2 = target.y - to.top
    const middle = (y1 + y2) / 2
    return { d: `M${source.x},${y1} V${middle} H${target.x} V${y2}`, x: target.x + 176, y: middle + 25, labelSpace: 160 }
  }
  if (Math.abs(dx) > Math.abs(dy)) {
    const direction = Math.sign(dx)
    const x1 = source.x + direction * from.side
    const x2 = target.x - direction * to.side
    const mid = (x1 + x2) / 2
    return { d: `M${x1},${source.y} C${mid},${source.y} ${mid},${target.y} ${x2},${target.y}`, x: mid, y: (source.y + target.y) / 2 - 16, labelSpace: Math.abs(x2 - x1) - 12 }
  }
  const down = dy > 0
  const y1 = source.y + (down ? from.bottom : -from.top)
  const y2 = target.y + (down ? -to.top : to.bottom)
  const mid = (y1 + y2) / 2
  return { d: `M${source.x},${y1} C${source.x},${mid} ${target.x},${mid} ${target.x},${y2}`, x: (source.x + target.x) / 2 + 85, y: mid + 4, labelSpace: 170 }
}

function activate(event: KeyboardEvent<SVGGElement>, action: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

export function Graph({ scene, step, onSelect }: { scene: Scene; step: WalkthroughStep | null; onSelect: (selection: InspectorSelection) => void }) {
  const [hovered, setHovered] = useState<GraphNode | null>(null)
  const scroll = useRef<HTMLDivElement>(null)
  const layout = useMemo(() => layoutScene(scene), [scene])
  useEffect(() => {
    const container = scroll.current
    if (!step || !container) return
    const active = layout.nodes.filter(node => step.nodes.includes(node.id))
    if (!active.length) return
    const minX = Math.min(...active.map(node => node.x))
    const maxX = Math.max(...active.map(node => node.x))
    const minY = Math.min(...active.map(node => node.y))
    const maxY = Math.max(...active.map(node => node.y))
    const destination = layout.nodes.find(node => node.id === step.nodes.at(-1)) ?? active[0]
    const scale = container.scrollWidth / layout.width
    const x = (maxX - minX + 200) * scale > container.clientWidth ? destination.x : (minX + maxX) / 2
    const y = (maxY - minY + 196) * scale > container.clientHeight ? destination.y : (minY + maxY) / 2
    const behavior = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
    container.scrollTo({ left: x * container.scrollWidth / layout.width - container.clientWidth / 2, top: y * container.scrollHeight / layout.height - container.clientHeight / 2, behavior })
    if (container.scrollHeight > container.clientHeight || container.scrollWidth > container.clientWidth) container.scrollIntoView({ block: 'start', behavior })
  }, [step, layout])
  return <div ref={scroll} className="graph-scroll" aria-label="Collaboration map">
    <div className="graph-canvas">
      <svg className="collaboration-graph" viewBox={`0 0 ${layout.width} ${layout.height}`} aria-label={`${scene.title}: expected architecture`}>
        <defs>
          <marker id="arrow-neutral" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M1 1 8 5 1 9" fill="none" stroke="currentColor" strokeWidth="1.5" /></marker>
          <marker id="arrow-active" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M1 1 8 5 1 9" fill="none" stroke="#0766eb" strokeWidth="1.5" /></marker>
        </defs>
        <g className="graph-groups" aria-hidden="true">
          {layout.groups.map(group => <g key={group.id}><rect x={group.x} y={group.y} width={group.width} height={group.height} rx="18" /><text x={group.x + 22} y={group.y + 30}>{group.label}</text></g>)}
        </g>
        <g className="graph-edges">
          {scene.edges.map(edge => {
            const source = layout.nodes.find(node => node.id === edge.source)
            const target = layout.nodes.find(node => node.id === edge.target)
            if (!source || !target) return null
            const line = connection(source, target)
            const active = step ? step.edges.includes(edge.id) : edge.emphasis
            const marker = active ? 'url(#arrow-active)' : 'url(#arrow-neutral)'
            return <g key={edge.id} className={`graph-edge ${active ? 'is-active' : ''}`} role="button" tabIndex={0} aria-label={`Explore connection: ${components[edge.source].label} to ${components[edge.target].label}${edge.label ? `, ${edge.label}` : ''}`} onClick={() => onSelect({ kind: 'edge', id: edge.id })} onKeyDown={event => activate(event, () => onSelect({ kind: 'edge', id: edge.id }))}>
              <title>{edge.summary}</title>
              <path className="edge-hit" d={line.d} />
              <path className="edge-line" d={line.d} markerEnd={marker} markerStart={edge.bidirectional ? marker : undefined} />
              {edge.label && edge.label.length * 7.8 + 20 <= line.labelSpace && <g className={`edge-label ${edge.emphasis || (step && active) ? 'is-visible' : ''}`}><rect x={line.x - edge.label.length * 3.9 - 10} y={line.y - 16} width={edge.label.length * 7.8 + 20} height={29} rx={7} /><text x={line.x} y={line.y + 2} textAnchor="middle">{edge.label}</text></g>}
            </g>
          })}
        </g>
        {layout.nodes.map(node => {
          const definition = components[node.id]
          const compact = definition.kind === 'service' || node.id === 'preflight'
          const label = node.label ?? (node.id === 'preflight' ? 'Preflight' : definition.label)
          const role = node.id === 'preflight' ? 'Provenance' : node.role ?? definition.role
          const active = step?.nodes.includes(node.id)
          return <foreignObject key={node.id} data-node={node.id} x={node.x - 92} y={node.y - 80} width="184" height="180" className={`graph-node ${active ? 'is-active' : ''}`}>
            <button className={`node-button node-${compact ? 'service' : definition.kind} identity-${node.id} ${node.id === 'preflight' ? 'compact-agent' : ''}`} onMouseEnter={() => setHovered(node)} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered(node)} onBlur={() => setHovered(null)} onClick={() => { setHovered(null); onSelect({ kind: 'node', id: node.id }) }} aria-label={`Explore ${label}: ${role}`}>
              <span className={`node-tile tile-${node.id}`}><Icon name={node.id} size={!compact && definition.kind === 'agent' ? 48 : 28} />{compact && <span>{label}</span>}</span>
              {!compact && <span className="node-name">{label}</span>}
              <span className="node-role">{role}</span>
            </button>
          </foreignObject>
        })}
      </svg>
      {hovered && !step && <div className="node-tooltip" role="tooltip" style={{ left: `${Math.min(85, Math.max(15, hovered.x / layout.width * 100))}%`, top: `${Math.min(81, (hovered.y + 105) / layout.height * 100)}%` }}><strong>{components[hovered.id].kind === 'agent' ? 'Reasoning agent' : components[hovered.id].kind === 'service' ? 'Deterministic service' : 'Workflow context'}</strong><span>{components[hovered.id].summary}</span><small>Click to explore</small></div>}
    </div>
  </div>
}
