import type { PageResponse } from '@/types/api'

export type KnowledgeBaseStatus = 'active' | 'disabled'
export type DocumentStatus = 'uploaded' | 'published' | 'disabled' | 'deleted'
export type DocumentVersionStatus =
  | 'uploading'
  | 'awaiting_pipeline'
  | 'processing'
  | 'published'
  | 'superseded'
  | 'failed'
export type IngestionJobStatus =
  'awaiting_pipeline' | 'processing' | 'completed' | 'failed'
export type OutboxEventStatus = 'pending' | 'published' | 'failed'

export interface KnowledgeBase {
  id: string
  name: string
  description: string | null
  embedding_provider: string
  embedding_model: string
  embedding_dimensions: number
  embedding_distance_metric: string
  pipeline_version: string
  status: KnowledgeBaseStatus
  search_enabled: boolean
  created_at: string
  updated_at: string
}

export interface KnowledgeBaseList extends PageResponse {
  items: KnowledgeBase[]
}

export interface KnowledgeBaseInput {
  name: string
  description?: string | null
}

export interface KnowledgeBaseUpdate {
  name?: string
  description?: string | null
  status?: KnowledgeBaseStatus
  search_enabled?: boolean
}

export interface Document {
  id: string
  knowledge_base_id: string
  name: string
  mime_type: string
  size_bytes: number
  content_hash: string
  status: DocumentStatus
  is_enabled: boolean
  created_at: string
  updated_at: string
}

export interface DocumentList extends PageResponse {
  items: Document[]
}

export interface DocumentVersion {
  id: string
  document_id: string
  version: number
  content_hash: string
  status: DocumentVersionStatus
  pipeline_version: string
  embedding_provider: string
  embedding_model: string
  embedding_dimensions: number
  error_code: string | null
  error_message: string | null
  metadata_json: Record<string, string>
  created_at: string
}

export interface DocumentVersionList {
  items: DocumentVersion[]
}

export interface IngestionJob {
  id: string
  document_id: string
  document_version_id: string
  status: IngestionJobStatus
  progress: number
  retry_count: number
  max_retries: number
  manual_retry_count: number
  error_code: string | null
  error_message: string | null
  error_detail: Record<string, unknown> | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface IngestionJobList {
  items: IngestionJob[]
}

export interface OutboxEvent {
  id: string
  ingestion_job_id: string
  status: OutboxEventStatus
  attempt_count: number
  max_attempts: number
  manual_retry_count: number
  available_at: string
  last_error: string | null
  published_at: string | null
  failed_at: string | null
}

export interface IngestionRetryResponse {
  ingestion_job: IngestionJob
  dispatch_event: OutboxEvent
}

export interface DocumentUploadResponse {
  document: Document
  version: DocumentVersion
  ingestion_job: IngestionJob
}

export interface DocumentDownloadUrl {
  url: string
  expires_at: string
}

export interface RetrievalInput {
  query: string
  limit?: number
  min_score?: number | null
}

export interface RetrievedChunk {
  chunk_id: string
  document_id: string
  document_version_id: string
  knowledge_base_id: string
  content: string
  title: string
  page_number: number | null
  section_path: string | null
  sheet_name: string | null
  row_start: number | null
  row_end: number | null
  char_start: number | null
  char_end: number | null
  metadata: Record<string, unknown>
  score: number
  retrieval_source: string
}

export interface RetrievalResponse {
  knowledge_base_id: string
  query: string
  embedding_model: string
  latency_ms: number
  items: RetrievedChunk[]
}
