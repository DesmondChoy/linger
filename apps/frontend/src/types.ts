export type Message = {
  role: 'user' | 'assistant'
  content: string
}

export type Memory = {
  memory_id: string
  text: string
  capture_type: 'explicit' | 'automatic' | 'correction'
  evidence_ids: string[]
  created_at: string
  updated_at: string
}

export type MemoryState = {
  capture_enabled: boolean
  memories: Memory[]
}

export type MemorySaveResult = {
  memory: Memory
  created: boolean
}
