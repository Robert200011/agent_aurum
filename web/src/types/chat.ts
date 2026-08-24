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
export type ResponseDepth = 'brief' | 'standard' | 'deep'
export type ResponseDepthRequest = 'auto' | ResponseDepth
export type FinancialAnalysisType =
  | 'transaction_lookup'
  | 'cashflow_review'
  | 'budget_review'
  | 'financial_health'
  | 'portfolio_review'
  | 'goal_progress'
  | 'investment_education'
  | 'mixed'

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
  analysis_type: FinancialAnalysisType | null
  response_depth: ResponseDepth | null
  fast_path: boolean
}

export interface StructuredAnswer {
  message_id: string
  answer: string
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
