import type { ChatSource } from '../types'

/** Human-readable footer text for one used source; never echoes memory content. */
export function formatSourceLabel(source: ChatSource): string {
  if (source.kind === 'book' && source.location) {
    return `${source.label} — ${source.location}`
  }
  return source.label
}
