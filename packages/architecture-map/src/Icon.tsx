import type { ReactNode } from 'react'
import type { ComponentId } from './types'

type IconName = ComponentId | 'chevron' | 'play' | 'close' | 'back' | 'forward' | 'info' | 'history' | 'layers' | 'checklist' | 'arrow'

const glyphs: Record<IconName, ReactNode> = {
  muse: <><path d="m6 25 3-9L24 3c3-2 6 1 4 4L15 23l-9 2Z" /><path d="m9 16 6 7M7 25l-3 3M17 10l5 5" /></>,
  librarian: <><path d="M16 8C12 4 7 4 3 5v21c4-1 9-1 13 2 4-3 9-3 13-2V5c-4-1-9-1-13 3ZM16 8v20" /><path d="M7 10c2-.3 4 0 6 1M7 15c2-.3 4 0 6 1M20 11c2-1 4-1 5-1M20 16c2-1 4-1 5-1" /></>,
  provenance: <><path d="m16 3 11 4v8c0 7-5 11-11 14C10 26 5 22 5 15V7l11-4Z" /><path d="M12 12h8M12 17h8M16 22v-1" /></>,
  preflight: <><path d="m16 4 10 4v7c0 6-4 10-10 13C10 25 6 21 6 15V8l10-4Z" /><path d="M12 16h8M16 12v8" /></>,
  release: <><rect x="5" y="5" width="22" height="22" rx="5" /><path d="M11 11h10M11 16h6M11 21h10" /></>,
  input: <><path d="M7 5h18a3 3 0 0 1 3 3v13a3 3 0 0 1-3 3H13l-8 5V8a3 3 0 0 1 2-3Z" /><path d="M10 11h12M10 16h8" /></>,
  response: <><path d="M7 5h18a3 3 0 0 1 3 3v13a3 3 0 0 1-3 3h-5l-7 5v-5H7a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3Z" /><path d="M10 11h12M10 16h8" /></>,
  corpus: <><rect x="5" y="3" width="22" height="26" rx="3" /><path d="M10 3v26M15 10h7M15 15h7M15 20h4" /></>,
  sculptor: <><path d="m5 21 4-15 13-3 7 12-7 14-17-8ZM9 6l5 12 15-3M14 18l8 11M14 18l8-15M5 21l9-3" /></>,
  serendipity: <><circle cx="8" cy="9" r="4" /><circle cx="25" cy="12" r="4" /><circle cx="15" cy="26" r="4" /><path d="m12 10 9 1M10 13l4 9M23 16l-6 6" /></>,
  memory_policy: <><rect x="5" y="4" width="22" height="25" rx="5" /><path d="M11 11h10M11 18h10" /><circle cx="14" cy="11" r="2" fill="currentColor" stroke="none" /><circle cx="19" cy="18" r="2" fill="currentColor" stroke="none" /></>,
  memory: <><ellipse cx="16" cy="7" rx="11" ry="4" /><path d="M5 7v17c0 2 5 5 11 5s11-3 11-5V7M5 15c0 2 5 4 11 4s11-2 11-4" /></>,
  web: <><circle cx="16" cy="16" r="13" /><ellipse cx="16" cy="16" rx="6" ry="13" /><path d="M3 16h26M6 8h20M6 24h20" /></>,
  session: <><path d="M8 9h19v18H8zM4 22V5h18" /><path d="M13 15h9M13 21h6" /></>,
  capture_review: <><rect x="5" y="7" width="22" height="20" rx="4" /><path d="M11 7V4h10v3M11 15h10M11 21h6" /></>,
  curation_review: <><path d="m16 3 11 4v8c0 7-5 11-11 14C10 26 5 22 5 15V7l11-4Z" /><path d="M11 13h10M11 18h10" /></>,
  proposal: <><path d="M7 3h13l6 6v20H7V3ZM20 3v7h6" /><path d="M12 15h9M12 20h9M12 25h5" /></>,
  chevron: <path d="m9 13 7 7 7-7" />,
  play: <path d="m11 6 15 10-15 10V6Z" />,
  close: <path d="m9 9 14 14M23 9 9 23" />,
  back: <path d="m20 7-9 9 9 9" />,
  forward: <path d="m12 7 9 9-9 9" />,
  info: <><circle cx="16" cy="16" r="12" /><path d="M16 14v9M16 8v1" /></>,
  history: <><path d="M5 13a12 12 0 1 1 2 12M5 5v8h8M16 9v8l5 3" /></>,
  layers: <><path d="m3 11 13-7 13 7-13 7L3 11ZM3 18l13 7 13-7M3 24l13 7 13-7" /></>,
  checklist: <><path d="M13 8h15M13 16h15M13 24h15M3 7l2 2 4-4M3 15l2 2 4-4M3 23l2 2 4-4" /></>,
  arrow: <path d="M5 16h22m-8-8 8 8-8 8" />,
}

export function Icon({ name, size = 24, className = '' }: { name: IconName; size?: number; className?: string }) {
  return <svg className={className} width={size} height={size} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{glyphs[name]}</svg>
}
