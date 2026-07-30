import type { PageResponse } from '@/types/api'

export type ConversationStatus = 'active' | 'archived'
export type MessageRole = 'user' | 'assistant'
export type MessageStatus =
  | 'pending'
  | 'streaming'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface ChatProject {
  id: string
  name: string
  description: string | null
}

export interface ChatProjectList {
  items: ChatProject[]
}

export interface Conversation {
  id: string
  project_id: string | null
  title: string
  status: ConversationStatus
  created_at: string
  updated_at: string
}

export interface ConversationList extends PageResponse {
  items: Conversation[]
}

export interface MessageCitation {
  citation_id: number
  document_id: string
  document_version_id: string
  knowledge_base_id: string
  chunk_id: string
  title: string
  document_version: number
  page: number | null
  section: string | null
  sheet_name: string | null
  row_start: number | null
  row_end: number | null
  char_start: number | null
  char_end: number | null
  content_hash: string
  quote: string
  score: number | null
}

export interface ChatMessage {
  id: string
  conversation_id: string
  role: MessageRole
  content: string
  status: MessageStatus
  model: string | null
  prompt_tokens: number | null
  completion_tokens: number | null
  latency_ms: number | null
  created_at: string
  citations: MessageCitation[]
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[]
}

export interface StructuredAnswer {
  message_id: string
  answer: string
  citations: MessageCitation[]
  data_as_of: string | null
  risk_notice: string | null
}

export interface ChatStreamStarted {
  message_id: string
  run_id: string
}

export interface ChatStreamDelta {
  delta: string
}

export interface ChatStreamError {
  code: string
  message: string
  request_id: string | null
}
