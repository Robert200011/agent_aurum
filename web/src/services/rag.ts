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
  Project,
  ProjectInput,
  ProjectKnowledgeBaseBinding,
  ProjectList,
  ProjectUpdate,
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
  async listProjects(): Promise<ProjectList> {
    const response = await http.get<ProjectList>('/admin/projects', {
      params: { page: 1, page_size: 200 },
    })
    return response.data
  },
  async createProject(payload: ProjectInput): Promise<Project> {
    const response = await http.post<Project>('/admin/projects', payload)
    return response.data
  },
  async updateProject(
    projectId: string,
    payload: ProjectUpdate,
  ): Promise<Project> {
    const response = await http.patch<Project>(
      `/admin/projects/${projectId}`,
      payload,
    )
    return response.data
  },
  async deleteProject(projectId: string): Promise<void> {
    await http.delete(`/admin/projects/${projectId}`)
  },

  async listKnowledgeBases(): Promise<KnowledgeBaseList> {
    const response = await http.get<KnowledgeBaseList>(
      '/admin/knowledge-bases',
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
      '/admin/knowledge-bases',
      payload,
    )
    return response.data
  },
  async updateKnowledgeBase(
    knowledgeBaseId: string,
    payload: KnowledgeBaseUpdate,
  ): Promise<KnowledgeBase> {
    const response = await http.patch<KnowledgeBase>(
      `/admin/knowledge-bases/${knowledgeBaseId}`,
      payload,
    )
    return response.data
  },
  async publishKnowledgeBase(knowledgeBaseId: string): Promise<KnowledgeBase> {
    const response = await http.post<KnowledgeBase>(
      `/admin/knowledge-bases/${knowledgeBaseId}/publish`,
    )
    return response.data
  },
  async disableKnowledgeBase(knowledgeBaseId: string): Promise<KnowledgeBase> {
    const response = await http.post<KnowledgeBase>(
      `/admin/knowledge-bases/${knowledgeBaseId}/disable`,
    )
    return response.data
  },
  async deleteKnowledgeBase(knowledgeBaseId: string): Promise<void> {
    await http.delete(`/admin/knowledge-bases/${knowledgeBaseId}`)
  },
  async listKnowledgeBaseProjects(
    knowledgeBaseId: string,
  ): Promise<ProjectKnowledgeBaseBinding[]> {
    const response = await http.get<ProjectKnowledgeBaseBinding[]>(
      `/admin/knowledge-bases/${knowledgeBaseId}/projects`,
    )
    return response.data
  },
  async bindKnowledgeBase(
    knowledgeBaseId: string,
    projectId: string,
  ): Promise<ProjectKnowledgeBaseBinding> {
    const response = await http.post<ProjectKnowledgeBaseBinding>(
      `/admin/knowledge-bases/${knowledgeBaseId}/projects`,
      { project_id: projectId },
    )
    return response.data
  },
  async unbindKnowledgeBase(
    knowledgeBaseId: string,
    projectId: string,
  ): Promise<void> {
    await http.delete(
      `/admin/knowledge-bases/${knowledgeBaseId}/projects/${projectId}`,
    )
  },

  async listDocuments(knowledgeBaseId: string): Promise<DocumentList> {
    const response = await http.get<DocumentList>(
      `/admin/knowledge-bases/${knowledgeBaseId}/documents`,
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
      `/admin/knowledge-bases/${knowledgeBaseId}/documents`,
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
      `/admin/documents/${documentId}/versions`,
      uploadForm(file, metadata),
      { headers: { 'Idempotency-Key': idempotencyKey }, timeout: 90_000 },
    )
    return response.data
  },
  async listDocumentVersions(documentId: string): Promise<DocumentVersionList> {
    const response = await http.get<DocumentVersionList>(
      `/admin/documents/${documentId}/versions`,
    )
    return response.data
  },
  async getDownloadUrl(
    documentVersionId: string,
  ): Promise<DocumentDownloadUrl> {
    const response = await http.get<DocumentDownloadUrl>(
      `/admin/document-versions/${documentVersionId}/download-url`,
    )
    return response.data
  },
  async disableDocument(documentId: string): Promise<Document> {
    const response = await http.post<Document>(
      `/admin/documents/${documentId}/disable`,
    )
    return response.data
  },
  async deleteDocument(documentId: string): Promise<void> {
    await http.delete(`/admin/documents/${documentId}`)
  },

  async listIngestionJobs(documentId: string): Promise<IngestionJobList> {
    const response = await http.get<IngestionJobList>(
      `/admin/documents/${documentId}/ingestion-jobs`,
    )
    return response.data
  },
  async getIngestionJob(jobId: string): Promise<IngestionJob> {
    const response = await http.get<IngestionJob>(
      `/admin/ingestion-jobs/${jobId}`,
    )
    return response.data
  },
  async retryIngestionJob(jobId: string): Promise<IngestionRetryResponse> {
    const response = await http.post<IngestionRetryResponse>(
      `/admin/ingestion-jobs/${jobId}/retry`,
    )
    return response.data
  },
  async retryIngestionDispatch(jobId: string): Promise<OutboxEvent> {
    const response = await http.post<OutboxEvent>(
      `/admin/ingestion-jobs/${jobId}/retry-dispatch`,
    )
    return response.data
  },

  async retrieve(
    knowledgeBaseId: string,
    payload: RetrievalInput,
  ): Promise<RetrievalResponse> {
    const response = await http.post<RetrievalResponse>(
      `/admin/knowledge-bases/${knowledgeBaseId}/retrieve`,
      payload,
      { timeout: 45_000 },
    )
    return response.data
  },
}
