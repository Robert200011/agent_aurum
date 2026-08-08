import { http } from '@/services/http'
import type {
  Document,
  DocumentDownloadUrl,
  DocumentList,
  DocumentUploadResponse,
  DocumentVersionList,
  IngestionJob,
  IngestionJobList,
  IngestionRetryResponse,
  KnowledgeBase,
  KnowledgeBaseInput,
  KnowledgeBaseList,
  KnowledgeBaseUpdate,
  OutboxEvent,
  RetrievalInput,
  RetrievalResponse,
} from '@/types/rag'

function uploadForm(file: File, metadata: Record<string, string>): FormData {
  const form = new FormData()
  form.append('file', file)
  if (Object.keys(metadata).length) {
    form.append('metadata', JSON.stringify(metadata))
  }
  return form
}

export const ragApi = {
  async listKnowledgeBases(): Promise<KnowledgeBaseList> {
    const response = await http.get<KnowledgeBaseList>(
      '/knowledge-bases',
      {
        params: { page: 1, page_size: 200 },
      },
    )
    return response.data
  },
  async createKnowledgeBase(
    payload: KnowledgeBaseInput,
  ): Promise<KnowledgeBase> {
    const response = await http.post<KnowledgeBase>(
      '/knowledge-bases',
      payload,
    )
    return response.data
  },
  async updateKnowledgeBase(
    knowledgeBaseId: string,
    payload: KnowledgeBaseUpdate,
  ): Promise<KnowledgeBase> {
    const response = await http.patch<KnowledgeBase>(
      `/knowledge-bases/${knowledgeBaseId}`,
      payload,
    )
    return response.data
  },
  async disableKnowledgeBase(knowledgeBaseId: string): Promise<KnowledgeBase> {
    const response = await http.patch<KnowledgeBase>(
      `/knowledge-bases/${knowledgeBaseId}`,
      { status: 'disabled' },
    )
    return response.data
  },
  async enableKnowledgeBase(knowledgeBaseId: string): Promise<KnowledgeBase> {
    const response = await http.patch<KnowledgeBase>(
      `/knowledge-bases/${knowledgeBaseId}`,
      { status: 'active' },
    )
    return response.data
  },
  async deleteKnowledgeBase(knowledgeBaseId: string): Promise<void> {
    await http.delete(`/knowledge-bases/${knowledgeBaseId}`)
  },

  async listDocuments(knowledgeBaseId: string): Promise<DocumentList> {
    const response = await http.get<DocumentList>(
      `/knowledge-bases/${knowledgeBaseId}/documents`,
      { params: { page: 1, page_size: 200 } },
    )
    return response.data
  },
  async uploadDocument(
    knowledgeBaseId: string,
    file: File,
    metadata: Record<string, string>,
    idempotencyKey: string,
  ): Promise<DocumentUploadResponse> {
    const response = await http.post<DocumentUploadResponse>(
      `/knowledge-bases/${knowledgeBaseId}/documents`,
      uploadForm(file, metadata),
      { headers: { 'Idempotency-Key': idempotencyKey }, timeout: 90_000 },
    )
    return response.data
  },
  async uploadDocumentVersion(
    documentId: string,
    file: File,
    metadata: Record<string, string>,
    idempotencyKey: string,
  ): Promise<DocumentUploadResponse> {
    const response = await http.post<DocumentUploadResponse>(
      `/documents/${documentId}/versions`,
      uploadForm(file, metadata),
      { headers: { 'Idempotency-Key': idempotencyKey }, timeout: 90_000 },
    )
    return response.data
  },
  async listDocumentVersions(documentId: string): Promise<DocumentVersionList> {
    const response = await http.get<DocumentVersionList>(
      `/documents/${documentId}/versions`,
    )
    return response.data
  },
  async getDownloadUrl(
    documentVersionId: string,
  ): Promise<DocumentDownloadUrl> {
    const response = await http.get<DocumentDownloadUrl>(
      `/document-versions/${documentVersionId}/download-url`,
    )
    return response.data
  },
  async disableDocument(documentId: string): Promise<Document> {
    const response = await http.post<Document>(
      `/documents/${documentId}/disable`,
    )
    return response.data
  },
  async deleteDocument(documentId: string): Promise<void> {
    await http.delete(`/documents/${documentId}`)
  },

  async listIngestionJobs(documentId: string): Promise<IngestionJobList> {
    const response = await http.get<IngestionJobList>(
      `/documents/${documentId}/ingestion-jobs`,
    )
    return response.data
  },
  async getIngestionJob(jobId: string): Promise<IngestionJob> {
    const response = await http.get<IngestionJob>(
      `/ingestion-jobs/${jobId}`,
    )
    return response.data
  },
  async retryIngestionJob(jobId: string): Promise<IngestionRetryResponse> {
    const response = await http.post<IngestionRetryResponse>(
      `/ingestion-jobs/${jobId}/retry`,
    )
    return response.data
  },
  async retryIngestionDispatch(jobId: string): Promise<OutboxEvent> {
    const response = await http.post<OutboxEvent>(
      `/ingestion-jobs/${jobId}/retry-dispatch`,
    )
    return response.data
  },

  async retrieve(
    knowledgeBaseId: string,
    payload: RetrievalInput,
  ): Promise<RetrievalResponse> {
    const response = await http.post<RetrievalResponse>(
      `/knowledge-bases/${knowledgeBaseId}/search-preview`,
      payload,
      { timeout: 45_000 },
    )
    return response.data
  },
}
