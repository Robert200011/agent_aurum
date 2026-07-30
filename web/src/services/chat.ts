import { http } from '@/services/http'
import type {
  ChatProjectList,
  Conversation,
  ConversationDetail,
  ConversationList,
  ConversationStatus,
  StructuredAnswer,
} from '@/types/chat'

export const chatApi = {
  async listProjects(): Promise<ChatProjectList> {
    const response = await http.get<ChatProjectList>('/chat/projects')
    return response.data
  },

  async listConversations(): Promise<ConversationList> {
    const response = await http.get<ConversationList>('/conversations', {
      params: { page: 1, page_size: 100 },
    })
    return response.data
  },

  async createConversation(
    projectId: string,
    title?: string,
  ): Promise<Conversation> {
    const response = await http.post<Conversation>('/conversations', {
      project_id: projectId,
      title: title?.trim() || null,
    })
    return response.data
  },

  async getConversation(conversationId: string): Promise<ConversationDetail> {
    const response = await http.get<ConversationDetail>(
      `/conversations/${conversationId}`,
    )
    return response.data
  },

  async updateConversation(
    conversationId: string,
    payload: { title?: string; status?: ConversationStatus },
  ): Promise<Conversation> {
    const response = await http.patch<Conversation>(
      `/conversations/${conversationId}`,
      payload,
    )
    return response.data
  },

  async ask(conversationId: string, question: string): Promise<StructuredAnswer> {
    const response = await http.post<StructuredAnswer>(
      `/conversations/${conversationId}/messages`,
      { question },
      { timeout: 90_000 },
    )
    return response.data
  },
}
