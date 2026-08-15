import type { PageResponse } from '@/types/api'

export type ConversationStatus = 'active' | 'archived'
export type MessageRole = 'user' | 'assistant'
export type MessageStatus =
  | 'pending'
  | 'streaming'
  | 'completed'
  | 'failed'
  | 'cancelled'
export type AgentRunStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
export type ChatGenerationStage =
  | 'understanding'
  | 'retrieving'
  | 'querying_finance'
  | 'analyzing'
  | 'generating'
  | 'finalizing'

export interface Conversation {
  id: string
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

export interface FinanceEvidenceFact {
  label: string
  value: string
  currency: string | null
  context: string | null
}

export interface MessageEvidence {
  evidence_id: string
  tool_call_id: string
  rank: number
  tool_name: string
  label: string
  data_as_of: string
  period_start: string | null
  period_end: string | null
  currencies: string[]
  calculation_basis: string
  facts: FinanceEvidenceFact[]
  warning_codes: string[]
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
  evidence: MessageEvidence[]
  memory_count: number
  data_as_of: string | null
  risk_notice: string | null
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[]
}

export interface AgentRun {
  id: string
  conversation_id: string
  message_id: string | null
  thread_id: string
  trace_id: string | null
  status: AgentRunStatus
  graph_version: string | null
  error_code: string | null
  latency_ms: number | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  finance_tool_count: number
  data_as_of: string | null
  risk_notice: string | null
}

export interface StructuredAnswer {
  message_id: string
  answer: string
  citations: MessageCitation[]
  evidence: MessageEvidence[]
  memory_count: number
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

export interface ChatStreamStatus {
  stage: ChatGenerationStage
}

export interface ChatStreamError {
  code: string
  message: string
  request_id: string | null
}

export interface MemorySavedEvent {
  memory_id: string | null
  category: 'goal' | 'preference' | 'constraint' | 'personal'
  title: string
  result: 'saved' | 'exists' | 'rejected'
  reason: string | null
}

export interface MemoryConfirmationItem {
  category: 'goal' | 'preference' | 'constraint' | 'personal'
  title: string
  content: string
}

export interface MemoryConfirmationEvent {
  confirmation_id: string
  expires_at: string
  items: MemoryConfirmationItem[]
}

export interface MemoryConfirmationResolution {
  status: 'accepted' | 'declined'
  results: MemorySavedEvent[]
}
