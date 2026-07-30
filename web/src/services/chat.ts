import { authorizedFetch, http } from '@/services/http'
import { consumeSseResponse } from '@/services/sse'
import type {
  ChatStreamDelta,
  ChatStreamError,
  ChatStreamStarted,
  ChatProjectList,
  Conversation,
  ConversationDetail,
  ConversationList,
  ConversationStatus,
  StructuredAnswer,
} from '@/types/chat'

export class ChatStreamRequestError extends Error {
  constructor(
    message: string,
    readonly code = 'stream_error',
    readonly requestId: string | null = null,
  ) {
    super(message)
    this.name = 'ChatStreamRequestError'
  }
}

interface ChatStreamHandlers {
  onStart?: (event: ChatStreamStarted) => void
  onDelta: (delta: string) => void
  onComplete?: (answer: StructuredAnswer) => void
}

async function responseError(response: Response): Promise<ChatStreamRequestError> {
  try {
    const payload = (await response.json()) as {
      error?: { code?: string; message?: string; request_id?: string | null }
    }
    return new ChatStreamRequestError(
      payload.error?.message || `流式问答请求失败（HTTP ${response.status}）`,
      payload.error?.code,
      payload.error?.request_id,
    )
  } catch {
    return new ChatStreamRequestError(`流式问答请求失败（HTTP ${response.status}）`)
  }
}

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

  async askStream(
    conversationId: string,
    question: string,
    handlers: ChatStreamHandlers,
    signal?: AbortSignal,
  ): Promise<StructuredAnswer> {
    const response = await authorizedFetch(
      `/conversations/${conversationId}/messages/stream`,
      {
        method: 'POST',
        headers: {
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question }),
        signal,
      },
    )
    if (!response.ok) throw await responseError(response)
    if (!response.headers.get('content-type')?.includes('text/event-stream')) {
      throw new ChatStreamRequestError('服务端未返回 SSE 流')
    }

    let completed: StructuredAnswer | null = null
    await consumeSseResponse(response, (event) => {
      let payload: unknown
      try {
        payload = JSON.parse(event.data)
      } catch {
        throw new ChatStreamRequestError('服务端返回了无效的 SSE 数据')
      }
      if (event.event === 'start') {
        handlers.onStart?.(payload as ChatStreamStarted)
      } else if (event.event === 'delta') {
        handlers.onDelta((payload as ChatStreamDelta).delta)
      } else if (event.event === 'complete') {
        completed = payload as StructuredAnswer
        handlers.onComplete?.(completed)
      } else if (event.event === 'error') {
        const error = payload as ChatStreamError
        throw new ChatStreamRequestError(error.message, error.code, error.request_id)
      }
    })
    if (completed === null) {
      throw new ChatStreamRequestError('SSE 流在回答完成前意外结束')
    }
    return completed
  },
}
