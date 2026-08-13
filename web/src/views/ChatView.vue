<script setup lang="ts">
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  EditOutlined,
  FileSearchOutlined,
  IdcardOutlined,
  InboxOutlined,
  MessageOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  SendOutlined,
  StopOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import AnswerContent from '@/components/chat/AnswerContent.vue'
import FinanceEvidencePanel from '@/components/chat/FinanceEvidencePanel.vue'
import FinancialProfilePanel from '@/components/profile/FinancialProfilePanel.vue'
import { ChatStreamRequestError, chatApi } from '@/services/chat'
import { apiErrorMessage } from '@/services/http'
import type {
  ChatGenerationStage,
  ChatMessage,
  Conversation,
  ConversationDetail,
  MessageCitation,
  MessageEvidence,
} from '@/types/chat'
import { citationLocation } from '@/utils/chat'

dayjs.extend(relativeTime)

const props = withDefaults(defineProps<{ embedded?: boolean }>(), {
  embedded: false,
})

const loading = ref(true)
const detailLoading = ref(false)
const saving = ref(false)
const sending = ref(false)
const conversations = ref<Conversation[]>([])
const activeConversation = ref<ConversationDetail | null>(null)
const conversationSearch = ref('')
const embeddedPage = ref<'chat' | 'profile'>('chat')
const question = ref('')
const pendingQuestion = ref('')
const streamingAnswer = ref('')
const streamingCitations = ref<MessageCitation[]>([])
const streamingEvidence = ref<MessageEvidence[]>([])
const streamingDataAsOf = ref<string | null>(null)
const streamingRiskNotice = ref<string | null>(null)
const streamingMessageId = ref<string | null>(null)
const activeRunId = ref<string | null>(null)
const generationStage = ref<ChatGenerationStage>('understanding')
const streamMode = ref<'new' | 'regenerate' | 'resume'>('new')
const stopping = ref(false)
const errorText = ref('')
const messageScroller = ref<HTMLElement | null>(null)
let streamAbortController: AbortController | null = null
let scrollFrame: number | null = null

const createOpen = ref(false)
const createTitle = ref('')
const renameOpen = ref(false)
const renameTitle = ref('')

const citationOpen = ref(false)
const selectedCitation = ref<MessageCitation | null>(null)

const canAsk = computed(
  () =>
    activeConversation.value?.status === 'active' &&
    Boolean(question.value.trim()) &&
    !sending.value,
)
const generationStatusText = computed(() => {
  if (generationStage.value === 'understanding') return '正在理解问题'
  if (generationStage.value === 'querying_finance') return '正在查询个人财务数据'
  if (generationStage.value === 'analyzing') return '正在分析财务证据和知识依据'
  if (generationStage.value === 'generating') return '正在生成回答'
  if (generationStage.value === 'finalizing') return '正在校验引用并保存'
  return '正在检索参考资料'
})
const conversationGroups = computed(() => {
  const groups = [
    { key: 'today', label: '今天', items: [] as Conversation[] },
    { key: 'week', label: '过去 7 天', items: [] as Conversation[] },
    { key: 'older', label: '更早', items: [] as Conversation[] },
  ]
  const today = dayjs().startOf('day')

  for (const conversation of conversations.value) {
    const updatedAt = dayjs(conversation.updated_at)
    if (updatedAt.isAfter(today) || updatedAt.isSame(today)) {
      groups[0]?.items.push(conversation)
    } else if (updatedAt.isAfter(today.subtract(7, 'day'))) {
      groups[1]?.items.push(conversation)
    } else {
      groups[2]?.items.push(conversation)
    }
  }

  return groups.filter((group) => group.items.length)
})

function displayAnswer(content: string, riskNotice: string | null): string {
  if (!riskNotice || !content.trimEnd().endsWith(riskNotice)) return content
  return content.trimEnd().slice(0, -riskNotice.length).trimEnd()
}

async function loadWorkspace(): Promise<void> {
  loading.value = true
  try {
    const conversationList = await chatApi.listConversations(conversationSearch.value)
    conversations.value = conversationList.items
    if (!props.embedded && conversations.value[0]) {
      await selectConversation(conversations.value[0].id)
    }
  } catch (error) {
    message.error(apiErrorMessage(error, '问答工作台加载失败'))
  } finally {
    loading.value = false
  }
}

async function refreshConversations(): Promise<void> {
  conversations.value = (
    await chatApi.listConversations(conversationSearch.value)
  ).items
}

async function searchConversations(): Promise<void> {
  await refreshConversations()
  if (
    activeConversation.value &&
    !conversations.value.some((item) => item.id === activeConversation.value?.id)
  ) {
    activeConversation.value = null
  }
}

function handleConversationSearchChange(): void {
  if (!conversationSearch.value) void searchConversations()
}

async function selectConversation(
  conversationId: string,
  recover = true,
): Promise<void> {
  if (detailLoading.value) return
  detailLoading.value = true
  errorText.value = ''
  try {
    activeConversation.value = await chatApi.getConversation(conversationId)
    await scrollToBottom()
    if (recover && !sending.value) {
      void recoverRunningAnswer(conversationId)
    }
  } catch (error) {
    message.error(apiErrorMessage(error, '会话加载失败'))
  } finally {
    detailLoading.value = false
  }
}

async function recoverRunningAnswer(conversationId: string): Promise<void> {
  if (sending.value || activeConversation.value?.id !== conversationId) return
  try {
    const run = await chatApi.latestRun(conversationId)
    if (!run || !['queued', 'running'].includes(run.status) || !run.message_id) {
      return
    }
    activeRunId.value = run.id
    streamingMessageId.value = run.message_id
    streamMode.value = 'resume'
    message.info('检测到尚未完成的回答，正在恢复连接')
    await runGeneration(conversationId, (handlers, signal) =>
      chatApi.resumeStream(conversationId, run.id, handlers, signal),
    )
  } catch (error) {
    errorText.value = apiErrorMessage(error, '运行中的回答恢复失败')
  }
}

function openCreate(): void {
  createTitle.value = ''
  createOpen.value = true
}

function openFinancialProfile(): void {
  if (!props.embedded || sending.value) return
  embeddedPage.value = 'profile'
}

function closeFinancialProfile(): void {
  embeddedPage.value = 'chat'
}

async function startNewConversation(): Promise<void> {
  if (saving.value) return
  saving.value = true
  try {
    const created = await chatApi.createConversation()
    await refreshConversations()
    await selectConversation(created.id, false)
  } catch (error) {
    message.error(apiErrorMessage(error, '新会话创建失败'))
  } finally {
    saving.value = false
  }
}

function showConversationHistory(): void {
  if (sending.value) {
    message.info('回答生成完成后即可返回会话列表')
    return
  }
  activeConversation.value = null
  errorText.value = ''
}

async function createConversation(): Promise<void> {
  saving.value = true
  try {
    const created = await chatApi.createConversation(createTitle.value)
    createOpen.value = false
    await refreshConversations()
    await selectConversation(created.id)
    message.success('新会话已创建')
  } catch (error) {
    message.error(apiErrorMessage(error, '会话创建失败'))
  } finally {
    saving.value = false
  }
}

function openRename(): void {
  if (!activeConversation.value) return
  renameTitle.value = activeConversation.value.title
  renameOpen.value = true
}

async function renameConversation(): Promise<void> {
  if (!activeConversation.value || !renameTitle.value.trim()) {
    message.warning('请输入会话名称')
    return
  }
  saving.value = true
  try {
    const updated = await chatApi.updateConversation(
      activeConversation.value.id,
      { title: renameTitle.value.trim() },
    )
    activeConversation.value.title = updated.title
    renameOpen.value = false
    await refreshConversations()
    message.success('会话已重命名')
  } catch (error) {
    message.error(apiErrorMessage(error, '重命名失败'))
  } finally {
    saving.value = false
  }
}

function archiveConversation(): void {
  if (!activeConversation.value) return
  const conversationId = activeConversation.value.id
  Modal.confirm({
    title: '归档当前会话？',
    content: '归档后仍可查看历史消息和引用，但不能继续提问。',
    okText: '确认归档',
    cancelText: '取消',
    async onOk() {
      try {
        await chatApi.updateConversation(conversationId, {
          status: 'archived',
        })
        await Promise.all([
          selectConversation(conversationId),
          refreshConversations(),
        ])
        message.success('会话已归档')
      } catch (error) {
        message.error(apiErrorMessage(error, '归档失败'))
      }
    },
  })
}

function deleteConversation(): void {
  if (!activeConversation.value) return
  const conversationId = activeConversation.value.id
  Modal.confirm({
    title: '永久删除当前会话？',
    content: '会话消息、运行记录和可信引用将一并删除，且无法恢复。',
    okText: '永久删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await chatApi.deleteConversation(conversationId)
        activeConversation.value = null
        await refreshConversations()
        if (!props.embedded && conversations.value[0]) {
          await selectConversation(conversations.value[0].id)
        }
        message.success('会话已删除')
      } catch (error) {
        message.error(apiErrorMessage(error, '会话删除失败'))
      }
    },
  })
}

type StreamRequest = (
  handlers: {
    onStart: (event: { message_id: string; run_id: string }) => void
    onStatus: (event: { stage: ChatGenerationStage }) => void
    onDelta: (delta: string) => void
    onComplete: (answer: {
      answer: string
      citations: MessageCitation[]
      evidence: MessageEvidence[]
      data_as_of: string | null
      risk_notice: string | null
    }) => void
  },
  signal: AbortSignal,
) => Promise<unknown>

async function runGeneration(
  conversationId: string,
  request: StreamRequest,
): Promise<void> {
  streamingAnswer.value = ''
  streamingCitations.value = []
  streamingEvidence.value = []
  streamingDataAsOf.value = null
  streamingRiskNotice.value = null
  generationStage.value = 'understanding'
  errorText.value = ''
  stopping.value = false
  sending.value = true
  streamAbortController = new AbortController()
  await scrollToBottom()
  try {
    await request(
      {
        onStart(event) {
          activeRunId.value = event.run_id
          streamingMessageId.value = event.message_id
        },
        onStatus(event) {
          generationStage.value = event.stage
        },
        onDelta(delta) {
          streamingAnswer.value += delta
          scheduleScrollToBottom()
        },
        onComplete(answer) {
          streamingAnswer.value = answer.answer
          streamingCitations.value = answer.citations
          streamingEvidence.value = answer.evidence
          streamingDataAsOf.value = answer.data_as_of
          streamingRiskNotice.value = answer.risk_notice
          scheduleScrollToBottom()
        },
      },
      streamAbortController.signal,
    )
  } catch (error) {
    if (!stopping.value && !(error instanceof DOMException && error.name === 'AbortError')) {
      errorText.value =
        error instanceof ChatStreamRequestError
          ? error.message
          : apiErrorMessage(error, '回答生成失败，请稍后重试')
    }
  } finally {
    streamAbortController = null
    pendingQuestion.value = ''
    streamingAnswer.value = ''
    streamingCitations.value = []
    streamingEvidence.value = []
    streamingDataAsOf.value = null
    streamingRiskNotice.value = null
    streamingMessageId.value = null
    activeRunId.value = null
    sending.value = false
    const shouldRecover = !stopping.value && Boolean(errorText.value)
    stopping.value = false
    await selectConversation(conversationId, shouldRecover)
    try {
      await refreshConversations()
    } catch {
      message.warning('回答状态已更新，但会话列表刷新失败')
    }
    await scrollToBottom()
  }
}

async function submitQuestion(): Promise<void> {
  const conversation = activeConversation.value
  const normalized = question.value.trim()
  if (!conversation || !normalized || sending.value) return

  question.value = ''
  pendingQuestion.value = normalized
  streamMode.value = 'new'
  await runGeneration(conversation.id, (handlers, signal) =>
    chatApi.askStream(
      conversation.id,
      normalized,
      handlers,
      signal,
    ),
  )
}

async function regenerateAnswer(chatMessage: ChatMessage): Promise<void> {
  const conversation = activeConversation.value
  if (!conversation || sending.value || chatMessage.role !== 'assistant') return
  streamMode.value = 'regenerate'
  streamingMessageId.value = chatMessage.id
  chatMessage.content = ''
  chatMessage.citations = []
  chatMessage.evidence = []
  chatMessage.data_as_of = null
  chatMessage.risk_notice = null
  chatMessage.status = 'streaming'
  await runGeneration(conversation.id, (handlers, signal) =>
    chatApi.regenerateStream(
      conversation.id,
      chatMessage.id,
      handlers,
      signal,
    ),
  )
}

async function stopGeneration(): Promise<void> {
  const conversationId = activeConversation.value?.id
  const runId = activeRunId.value
  if (!conversationId || !runId || stopping.value) return
  stopping.value = true
  try {
    await chatApi.cancelRun(conversationId, runId)
    streamAbortController?.abort()
    message.success('已停止生成')
  } catch (error) {
    stopping.value = false
    message.error(apiErrorMessage(error, '停止生成失败'))
  }
}

function handleComposerKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    void submitQuestion()
  }
}

function openCitation(
  citations: MessageCitation[],
  citationId: number,
): void {
  const citation = citations.find((item) => item.citation_id === citationId)
  if (!citation) return
  selectedCitation.value = citation
  citationOpen.value = true
}

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (messageScroller.value) {
    messageScroller.value.scrollTop = messageScroller.value.scrollHeight
  }
}

function scheduleScrollToBottom(): void {
  if (scrollFrame !== null) return
  scrollFrame = window.requestAnimationFrame(() => {
    scrollFrame = null
    void scrollToBottom()
  })
}

onBeforeUnmount(() => {
  streamAbortController?.abort()
  if (scrollFrame !== null) window.cancelAnimationFrame(scrollFrame)
})

onMounted(loadWorkspace)
</script>

<template>
  <FinancialProfilePanel
    v-if="embedded && embeddedPage === 'profile'"
    @back="closeFinancialProfile"
  />
  <div v-else class="chat-page" :class="{ 'is-embedded': embedded }">
    <div v-if="!embedded" class="page-heading chat-heading">
      <div>
        <span class="heading-kicker">ROUTED ASSISTANT</span>
        <h1>智能问答</h1>
        <p>每轮问题按需选择直接回答或个人财务工具，并保留可核验依据。</p>
      </div>
      <a-button
        type="primary"
        size="large"
        @click="openCreate"
      >
        <PlusOutlined />新建会话
      </a-button>
    </div>

    <section
      class="chat-workspace"
      :class="{ 'surface-card': !embedded, 'has-active-chat': activeConversation }"
    >
      <aside class="conversation-panel">
        <template v-if="embedded">
          <div class="embedded-options">
            <span class="embedded-section-label">更多选项</span>
            <button
              type="button"
              :disabled="saving"
              @click="startNewConversation"
            >
              <PlusOutlined />
              <span>新建会话</span>
              <b>›</b>
            </button>
            <button type="button" @click="openCreate">
              <UserOutlined />
              <span>自定义会话名称</span>
              <b>›</b>
            </button>
            <button type="button" :disabled="sending" @click="openFinancialProfile">
              <IdcardOutlined />
              <span>个人财务档案</span>
              <b>›</b>
            </button>
          </div>
          <div class="embedded-recents-heading">
            <span class="embedded-section-label">最近会话</span>
            <a-button
              type="text"
              aria-label="刷新会话"
              :loading="loading"
              @click="refreshConversations"
            >
              <ReloadOutlined />
            </a-button>
          </div>
        </template>
        <div v-else class="panel-heading">
          <div>
            <span>CONVERSATIONS</span>
            <strong>我的会话</strong>
          </div>
          <a-button
            type="text"
            aria-label="刷新会话"
            :loading="loading"
            @click="refreshConversations"
          >
            <ReloadOutlined />
          </a-button>
        </div>
        <div v-if="!embedded" class="conversation-search">
          <a-input
            v-model:value="conversationSearch"
            allow-clear
            placeholder="搜索标题或历史消息"
            @press-enter="searchConversations"
            @change="handleConversationSearchChange"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
        </div>

        <a-skeleton :loading="loading" active :paragraph="{ rows: 5 }">
          <div v-if="conversations.length" class="conversation-list">
            <section
              v-for="group in conversationGroups"
              :key="group.key"
              class="conversation-group"
            >
              <span class="conversation-group-label">{{ group.label }}</span>
              <button
                v-for="conversation in group.items"
                :key="conversation.id"
                type="button"
                :class="[
                  'conversation-item',
                  {
                    active: activeConversation?.id === conversation.id,
                    archived: conversation.status === 'archived',
                  },
                ]"
                :disabled="sending"
                @click="selectConversation(conversation.id)"
              >
                <span v-if="!embedded" class="conversation-icon">
                  <MessageOutlined />
                </span>
                <span class="conversation-copy">
                  <strong>{{ conversation.title }}</strong>
                  <template v-if="!embedded">
                    <small>智能财务问答</small>
                    <time>{{ dayjs(conversation.updated_at).fromNow() }}</time>
                  </template>
                </span>
                <InboxOutlined
                  v-if="conversation.status === 'archived'"
                  class="archive-mark"
                />
                <span v-else-if="embedded" class="conversation-more">⋮</span>
              </button>
            </section>
          </div>
          <a-empty
            v-else
            :image="undefined"
            description="还没有问答会话"
            class="conversation-empty"
          >
            <a-button
              type="link"
              @click="embedded ? startNewConversation() : openCreate()"
            >
              创建第一个会话
            </a-button>
          </a-empty>
        </a-skeleton>
      </aside>

      <main class="message-panel">
        <template v-if="activeConversation">
          <header class="message-header">
            <div>
              <div class="title-row">
                <a-button
                  v-if="embedded"
                  type="text"
                  class="history-back"
                  aria-label="返回会话列表"
                  :disabled="sending"
                  @click="showConversationHistory"
                >
                  <ArrowLeftOutlined />
                </a-button>
                <strong>{{ activeConversation.title }}</strong>
                <a-tag
                  :color="
                    activeConversation.status === 'active' ? 'green' : 'default'
                  "
                >
                  {{
                    activeConversation.status === 'active' ? '进行中' : '已归档'
                  }}
                </a-tag>
              </div>
              <span>
                <RobotOutlined />
                个人财务数据按需调用
              </span>
            </div>
            <div class="header-actions">
              <a-tooltip title="重命名">
                <a-button type="text" aria-label="重命名会话" @click="openRename">
                  <EditOutlined />
                </a-button>
              </a-tooltip>
              <a-tooltip
                v-if="activeConversation.status === 'active'"
                title="归档"
              >
                <a-button
                  type="text"
                  aria-label="归档会话"
                  :disabled="sending"
                  @click="archiveConversation"
                >
                  <InboxOutlined />
                </a-button>
              </a-tooltip>
              <a-tooltip title="永久删除">
                <a-button
                  type="text"
                  danger
                  aria-label="删除会话"
                  :disabled="sending"
                  @click="deleteConversation"
                >
                  <DeleteOutlined />
                </a-button>
              </a-tooltip>
            </div>
          </header>

          <div
            ref="messageScroller"
            class="message-scroller"
            :class="{ loading: detailLoading }"
          >
            <div
              v-if="activeConversation.messages.length === 0 && !sending"
              class="welcome-state"
            >
              <div class="welcome-icon"><RobotOutlined /></div>
              <span>AURUM AI AGENT</span>
              <h2>今天想了解什么？</h2>
              <p>
                可以询问收支、预算与投资情况；重要结论会保留可核验依据。
              </p>
            </div>

            <article
              v-for="chatMessage in activeConversation.messages"
              :key="chatMessage.id"
              :class="['message-row', `is-${chatMessage.role}`]"
            >
              <div class="message-avatar">
                <UserOutlined v-if="chatMessage.role === 'user'" />
                <RobotOutlined v-else />
              </div>
              <div class="message-body">
                <div class="message-meta">
                  <strong>{{
                    chatMessage.role === 'user' ? '你' : 'Aurum'
                  }}</strong>
                  <time>{{ dayjs(chatMessage.created_at).format('HH:mm') }}</time>
                </div>
                <div
                  v-if="
                    chatMessage.role === 'assistant' &&
                      streamingMessageId === chatMessage.id &&
                      sending
                  "
                  class="streamed-answer"
                >
                  <FinanceEvidencePanel
                    :evidence="streamingEvidence"
                    :data-as-of="streamingDataAsOf"
                    :risk-notice="streamingRiskNotice"
                  />
                  <div v-if="streamingAnswer" class="answer-section-label">
                    分析建议
                  </div>
                  <AnswerContent
                    v-if="streamingAnswer"
                    :answer="displayAnswer(streamingAnswer, streamingRiskNotice)"
                    :citation-ids="
                      streamingCitations.map((citation) => citation.citation_id)
                    "
                    @citation="
                      (citationId) =>
                        openCitation(streamingCitations, citationId)
                    "
                  />
                  <div v-else class="thinking-indicator">
                    <i /><i /><i />
                    <span>{{ generationStatusText }}…</span>
                  </div>
                  <span
                    v-if="streamingAnswer && !streamingCitations.length"
                    class="streaming-caret"
                    aria-hidden="true"
                  />
                </div>
                <FinanceEvidencePanel
                  v-else-if="
                    chatMessage.role === 'assistant' &&
                      (chatMessage.evidence.length || chatMessage.risk_notice)
                  "
                  :evidence="chatMessage.evidence"
                  :data-as-of="chatMessage.data_as_of"
                  :risk-notice="chatMessage.risk_notice"
                />
                <div
                  v-if="
                    chatMessage.role === 'assistant' &&
                      ['failed', 'cancelled'].includes(chatMessage.status) &&
                      !chatMessage.content
                  "
                  class="failed-answer"
                >
                  {{
                    chatMessage.status === 'cancelled'
                      ? '本次回答已停止。'
                      : '本次回答生成失败。'
                  }}
                </div>
                <div
                  v-if="
                    chatMessage.role === 'assistant' &&
                      chatMessage.content &&
                      !(streamingMessageId === chatMessage.id && sending)
                  "
                  class="answer-section-label"
                >
                  分析建议
                </div>
                <AnswerContent
                  v-if="
                    chatMessage.role === 'assistant' &&
                      chatMessage.content &&
                      !(streamingMessageId === chatMessage.id && sending)
                  "
                  :answer="displayAnswer(chatMessage.content, chatMessage.risk_notice)"
                  :citation-ids="
                    chatMessage.citations.map((citation) => citation.citation_id)
                  "
                  @citation="
                    (citationId) =>
                      openCitation(chatMessage.citations, citationId)
                  "
                />
                <p v-if="chatMessage.role === 'user'" class="user-question">
                  {{ chatMessage.content }}
                </p>
                <div
                  v-if="
                    chatMessage.role === 'assistant' &&
                      chatMessage.citations.length &&
                      streamingMessageId !== chatMessage.id
                  "
                  class="message-sources"
                >
                  <span>参考依据</span>
                  <button
                    v-for="citation in chatMessage.citations"
                    :key="citation.chunk_id"
                    type="button"
                    @click="
                      openCitation(
                        chatMessage.citations,
                        citation.citation_id,
                      )
                    "
                  >
                    [{{ citation.citation_id }}] {{ citation.title }}
                  </button>
                </div>
                <div
                  v-if="
                    chatMessage.role === 'assistant' &&
                      ['completed', 'failed', 'cancelled'].includes(
                        chatMessage.status,
                      ) &&
                      activeConversation.status === 'active' &&
                      !sending
                  "
                  class="message-actions"
                >
                  <a-button
                    type="link"
                    size="small"
                    @click="regenerateAnswer(chatMessage)"
                  >
                    <ReloadOutlined />
                    {{
                      chatMessage.status === 'completed'
                        ? '重新生成'
                        : '重试回答'
                    }}
                  </a-button>
                </div>
              </div>
            </article>

            <template v-if="sending && streamMode === 'new'">
              <article class="message-row is-user pending">
                <div class="message-avatar"><UserOutlined /></div>
                <div class="message-body">
                  <div class="message-meta"><strong>你</strong></div>
                  <p class="user-question">{{ pendingQuestion }}</p>
                </div>
              </article>
              <article class="message-row is-assistant pending">
                <div class="message-avatar"><RobotOutlined /></div>
                <div class="message-body">
                  <div class="message-meta"><strong>Aurum</strong></div>
                  <div v-if="streamingAnswer" class="streamed-answer">
                    <FinanceEvidencePanel
                      :evidence="streamingEvidence"
                      :data-as-of="streamingDataAsOf"
                      :risk-notice="streamingRiskNotice"
                    />
                    <div class="answer-section-label">分析建议</div>
                    <AnswerContent
                      :answer="displayAnswer(streamingAnswer, streamingRiskNotice)"
                      :citation-ids="
                        streamingCitations.map((citation) => citation.citation_id)
                      "
                      @citation="
                        (citationId) =>
                          openCitation(streamingCitations, citationId)
                      "
                    />
                    <span
                      v-if="streamingCitations.length === 0"
                      class="streaming-caret"
                      aria-hidden="true"
                    />
                    <div
                      v-if="streamingCitations.length"
                      class="message-sources"
                    >
                      <span>参考依据</span>
                      <button
                        v-for="citation in streamingCitations"
                        :key="citation.chunk_id"
                        type="button"
                        @click="
                          openCitation(
                            streamingCitations,
                            citation.citation_id,
                          )
                        "
                      >
                        [{{ citation.citation_id }}] {{ citation.title }}
                      </button>
                    </div>
                  </div>
                  <div v-else class="thinking-indicator">
                    <i /><i /><i />
                    <span>{{ generationStatusText }}…</span>
                  </div>
                </div>
              </article>
            </template>
          </div>

          <footer class="composer">
            <a-alert
              v-if="errorText"
              type="error"
              show-icon
              closable
              :message="errorText"
              @close="errorText = ''"
            />
            <div
              v-if="activeConversation.status === 'archived'"
              class="archived-notice"
            >
              <InboxOutlined />该会话已归档，仅供查看。
            </div>
            <div v-else class="composer-box">
              <a-textarea
                v-model:value="question"
                :auto-size="{ minRows: 2, maxRows: 6 }"
                :maxlength="2000"
                :disabled="sending"
                placeholder="问问 Aurum，例如：我这个月的主要支出是什么？"
                @keydown="handleComposerKeydown"
              />
              <div class="composer-actions">
                <span>{{
                  sending ? generationStatusText : 'Ctrl / ⌘ + Enter 发送'
                }}</span>
                <a-button
                  v-if="sending"
                  danger
                  shape="round"
                  :disabled="!activeRunId || stopping"
                  :loading="stopping"
                  @click="stopGeneration"
                >
                  <StopOutlined />停止生成
                </a-button>
                <a-button
                  v-else
                  type="primary"
                  shape="circle"
                  size="large"
                  aria-label="发送问题"
                  :disabled="!canAsk"
                  @click="submitQuestion"
                >
                  <SendOutlined />
                </a-button>
              </div>
            </div>
            <p class="answer-boundary">
              AI 回答可能有误；重要信息请通过引用原文复核。
            </p>
          </footer>
        </template>

        <div v-else class="no-conversation">
          <div><MessageOutlined /></div>
          <h2>选择或创建一个会话</h2>
          <p>会话不固定绑定知识范围，每轮问题都会重新判断所需数据。</p>
          <a-button
            type="primary"
            @click="openCreate"
          >
            <PlusOutlined />新建会话
          </a-button>
        </div>
      </main>
    </section>

    <a-modal
      v-model:open="createOpen"
      title="新建问答会话"
      ok-text="创建"
      cancel-text="取消"
      :confirm-loading="saving"
      @ok="createConversation"
    >
      <a-form layout="vertical" class="dialog-form">
        <a-form-item label="会话名称（可选）">
          <a-input
            v-model:value="createTitle"
            :maxlength="256"
            placeholder="留空后将使用第一个问题自动命名"
          />
        </a-form-item>
        <a-alert
          type="info"
          show-icon
          message="知识范围由每轮问题动态判断，不会固定绑定到会话"
        />
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="renameOpen"
      title="重命名会话"
      ok-text="保存"
      cancel-text="取消"
      :confirm-loading="saving"
      @ok="renameConversation"
    >
      <a-input
        v-model:value="renameTitle"
        :maxlength="256"
        placeholder="输入会话名称"
        @press-enter="renameConversation"
      />
    </a-modal>

    <a-drawer
      v-model:open="citationOpen"
      title="可信引用"
      placement="right"
      :width="430"
    >
      <article v-if="selectedCitation" class="citation-detail">
        <div class="citation-number">
          <FileSearchOutlined />
          引用 [{{ selectedCitation.citation_id }}]
        </div>
        <h2>{{ selectedCitation.title }}</h2>
        <p class="citation-location">
          {{ citationLocation(selectedCitation) }}
        </p>
        <dl>
          <div>
            <dt>文档版本</dt>
            <dd>v{{ selectedCitation.document_version }}</dd>
          </div>
          <div v-if="selectedCitation.score !== null">
            <dt>检索相关度</dt>
            <dd>{{ (selectedCitation.score * 100).toFixed(1) }}%</dd>
          </div>
        </dl>
        <section>
          <span>引用原文</span>
          <blockquote>{{ selectedCitation.quote }}</blockquote>
        </section>
        <a-alert
          type="success"
          show-icon
          message="此引用由服务端根据实际检索结果校验并持久化"
        />
      </article>
    </a-drawer>
  </div>
</template>

<style scoped>
.chat-page {
  display: grid;
  gap: 22px;
}

.chat-heading {
  align-items: center;
}

.heading-kicker {
  display: block;
  margin-bottom: 6px;
  color: var(--mint-700);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.18em;
}

.chat-workspace {
  display: grid;
  grid-template-columns: 270px minmax(0, 1fr);
  min-height: 680px;
  height: calc(100vh - 205px);
  max-height: 920px;
  overflow: hidden;
}

.conversation-panel {
  min-width: 0;
  border-right: 1px solid var(--line);
  background: #f8faf7;
}

.panel-heading,
.message-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 72px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
}

.panel-heading > div,
.message-header > div:first-child {
  display: grid;
  gap: 4px;
}

.panel-heading span {
  color: var(--ink-500);
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.14em;
}

.panel-heading strong {
  color: var(--ink-950);
  font-size: 16px;
}

.conversation-list {
  display: grid;
  gap: 6px;
  max-height: calc(100vh - 344px);
  padding: 12px;
  overflow-y: auto;
}

.conversation-search {
  padding: 11px 12px 0;
}

.conversation-search :deep(.ant-input-affix-wrapper) {
  border-radius: 10px;
  background: white;
}

.conversation-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  gap: 9px;
  width: 100%;
  padding: 12px 10px;
  border: 1px solid transparent;
  border-radius: 12px;
  color: var(--ink-800);
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.conversation-item:hover {
  background: white;
}

.conversation-item.active {
  border-color: rgb(15 118 110 / 18%);
  background: white;
  box-shadow: 0 8px 24px rgb(11 37 34 / 7%);
}

.conversation-item.archived {
  opacity: 0.66;
}

.conversation-item:disabled {
  cursor: not-allowed;
}

.conversation-icon {
  display: grid;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  color: var(--mint-700);
  background: var(--mint-100);
  place-items: center;
}

.conversation-copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.conversation-copy strong,
.conversation-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-copy strong {
  font-size: 13px;
}

.conversation-copy small,
.conversation-copy time {
  color: var(--ink-500);
  font-size: 10px;
}

.archive-mark {
  margin-top: 4px;
  color: var(--ink-500);
}

.conversation-empty {
  margin-top: 80px;
}

.message-panel {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  background:
    radial-gradient(circle at 100% 0%, rgb(25 160 143 / 6%), transparent 24rem),
    white;
}

.message-header {
  flex: 0 0 auto;
  padding-inline: 22px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-row strong {
  max-width: min(55vw, 600px);
  overflow: hidden;
  color: var(--ink-950);
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-header > div:first-child > span {
  color: var(--ink-500);
  font-size: 11px;
}

.header-actions {
  display: flex;
}

.message-scroller {
  flex: 1 1 auto;
  min-height: 0;
  padding: 28px clamp(20px, 6vw, 82px);
  overflow-y: auto;
  scroll-behavior: smooth;
  transition: opacity 0.15s;
}

.message-scroller.loading {
  opacity: 0.58;
}

.welcome-state,
.no-conversation {
  display: grid;
  justify-items: center;
  max-width: 540px;
  margin: 10vh auto 0;
  text-align: center;
}

.welcome-icon,
.no-conversation > div {
  display: grid;
  width: 64px;
  height: 64px;
  margin-bottom: 16px;
  border: 1px solid rgb(15 118 110 / 16%);
  border-radius: 20px;
  color: var(--mint-700);
  background: var(--mint-100);
  font-size: 28px;
  box-shadow: 0 14px 34px rgb(15 118 110 / 12%);
  place-items: center;
}

.welcome-state > span {
  color: var(--mint-700);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.08em;
}

.welcome-state h2,
.no-conversation h2 {
  margin: 8px 0 6px;
  color: var(--ink-950);
  font-family: 'Iowan Old Style', 'Songti SC', serif;
  font-size: 26px;
}

.welcome-state p,
.no-conversation p {
  margin: 0 0 18px;
  color: var(--ink-500);
  line-height: 1.7;
}

.message-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 12px;
  max-width: 850px;
  margin: 0 auto 28px;
}

.message-avatar {
  display: grid;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  color: white;
  background: var(--ink-800);
  place-items: center;
}

.is-assistant .message-avatar {
  color: var(--mint-700);
  background: var(--mint-100);
}

.message-body {
  min-width: 0;
}

.message-meta {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 4px 0 8px;
}

.message-meta strong {
  color: var(--ink-800);
  font-size: 12px;
}

.message-meta time {
  color: var(--ink-500);
  font-size: 10px;
}

.user-question {
  display: inline-block;
  margin: 0;
  padding: 11px 15px;
  border-radius: 3px 14px 14px 14px;
  color: var(--ink-900);
  background: #f0f4f1;
  line-height: 1.7;
  white-space: pre-wrap;
}

.failed-answer {
  padding: 12px 14px;
  border: 1px solid rgb(216 79 79 / 18%);
  border-radius: 10px;
  color: var(--danger);
  background: rgb(216 79 79 / 6%);
}

.answer-section-label {
  margin: 4px 0 7px;
  color: var(--ink-500);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.08em;
}

.message-actions {
  display: flex;
  margin-top: 5px;
}

.message-actions :deep(.ant-btn) {
  padding-inline: 0;
  color: var(--ink-500);
  font-size: 11px;
}

.message-actions :deep(.ant-btn:hover) {
  color: var(--mint-700);
}

.message-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #edf1ee;
}

.message-sources > span {
  width: 100%;
  color: var(--ink-500);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.08em;
}

.message-sources button {
  max-width: 260px;
  padding: 5px 9px;
  overflow: hidden;
  border: 1px solid #dce6e1;
  border-radius: 8px;
  color: var(--ink-700);
  background: #fafcfb;
  cursor: pointer;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-sources button:hover {
  border-color: var(--mint-500);
  color: var(--mint-700);
}

.thinking-indicator {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--ink-500);
  font-size: 12px;
}

.thinking-indicator i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--mint-500);
  animation: thinking 1.1s infinite ease-in-out;
}

.thinking-indicator i:nth-child(2) {
  animation-delay: 0.14s;
}

.thinking-indicator i:nth-child(3) {
  margin-right: 5px;
  animation-delay: 0.28s;
}

.streamed-answer {
  position: relative;
}

.streaming-caret {
  display: inline-block;
  width: 2px;
  height: 1.1em;
  margin-left: 3px;
  vertical-align: -0.15em;
  background: var(--mint-600);
  animation: thinking 0.85s infinite ease-in-out;
}

.composer {
  flex: 0 0 auto;
  padding: 12px clamp(20px, 6vw, 82px) 14px;
  border-top: 1px solid var(--line);
  background: rgb(255 255 255 / 94%);
}

.composer > .ant-alert {
  max-width: 850px;
  margin: 0 auto 10px;
}

.composer-box {
  max-width: 850px;
  margin: 0 auto;
  padding: 11px 11px 9px 15px;
  border: 1px solid #cad9d2;
  border-radius: 15px;
  background: white;
  box-shadow: 0 12px 32px rgb(11 37 34 / 8%);
}

.composer-box:focus-within {
  border-color: var(--mint-500);
  box-shadow: 0 12px 34px rgb(15 118 110 / 12%);
}

.composer-box :deep(textarea) {
  padding: 0;
  border: 0;
  box-shadow: none !important;
  resize: none;
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}

.composer-actions span,
.answer-boundary {
  color: var(--ink-500);
  font-size: 10px;
}

.answer-boundary {
  margin: 7px auto 0;
  text-align: center;
}

.archived-notice {
  max-width: 850px;
  margin: 0 auto;
  padding: 13px;
  border-radius: 11px;
  color: var(--ink-500);
  background: #f1f4f2;
  text-align: center;
}

.no-conversation {
  margin-top: auto;
  margin-bottom: auto;
}

.dialog-form {
  margin-top: 20px;
}

.citation-detail h2 {
  margin: 14px 0 6px;
  color: var(--ink-950);
  font-size: 20px;
}

.citation-number {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
  border-radius: 8px;
  color: var(--mint-700);
  background: var(--mint-100);
  font-size: 12px;
  font-weight: 750;
}

.citation-location {
  color: var(--ink-500);
  line-height: 1.6;
}

.citation-detail dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 22px 0;
}

.citation-detail dl > div {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fafcfb;
}

.citation-detail dt,
.citation-detail section > span {
  color: var(--ink-500);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.08em;
}

.citation-detail dd {
  margin: 5px 0 0;
  color: var(--ink-900);
  font-weight: 700;
}

.citation-detail blockquote {
  margin: 8px 0 22px;
  padding: 16px;
  border-left: 3px solid var(--gold-500);
  border-radius: 0 10px 10px 0;
  color: var(--ink-800);
  background: #f7f8f4;
  line-height: 1.8;
  white-space: pre-wrap;
}

.chat-page.is-embedded {
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  gap: 0;
  overflow: hidden;
  background: #ffffff;
}

.is-embedded .chat-workspace {
  display: grid;
  width: 100%;
  height: 100%;
  min-height: 0;
  max-height: none;
  grid-template-columns: minmax(0, 1fr);
  overflow: hidden;
}

.is-embedded .conversation-panel,
.is-embedded .message-panel {
  min-width: 0;
  min-height: 0;
  grid-area: 1 / 1;
}

.is-embedded .conversation-panel {
  border: 0;
  background: #ffffff;
  overflow-y: auto;
}

.is-embedded .chat-workspace.has-active-chat .conversation-panel,
.is-embedded .chat-workspace:not(.has-active-chat) .message-panel {
  display: none;
}

.embedded-options {
  padding: 18px 14px 8px;
}

.embedded-section-label,
.conversation-group-label {
  display: block;
  color: #a1a1a8;
  font-size: 8px;
  font-weight: 750;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.embedded-options > .embedded-section-label {
  margin: 0 0 12px 3px;
}

.embedded-options button {
  display: grid;
  align-items: center;
  width: 100%;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid #ececee;
  color: #323237;
  background: #ffffff;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.embedded-options button:first-of-type {
  border-radius: 8px 8px 0 0;
}

.embedded-options button + button {
  margin-top: -1px;
}

.embedded-options button:last-of-type {
  border-radius: 0 0 8px 8px;
}

.embedded-options button:hover {
  position: relative;
  z-index: 1;
  border-color: #ddd9ff;
  background: #faf9ff;
}

.embedded-options button:disabled {
  cursor: wait;
  opacity: 0.6;
}

.embedded-options button > .anticon {
  color: #74747b;
  font-size: 12px;
}

.embedded-options button b {
  color: #b1b1b6;
  font-size: 16px;
  font-weight: 400;
}

.embedded-recents-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 44px;
  padding: 8px 14px 3px 17px;
}

.embedded-recents-heading :deep(.ant-btn) {
  width: 28px;
  height: 28px;
  color: #9999a0;
}

.is-embedded .conversation-list {
  display: block;
  max-height: none;
  padding: 0 14px 20px;
  overflow: visible;
}

.conversation-group {
  display: grid;
}

.is-embedded .conversation-group {
  margin-bottom: 15px;
}

.is-embedded .conversation-group-label {
  margin: 0 0 8px 3px;
  color: #727279;
  font-size: 9px;
  letter-spacing: 0;
  text-transform: none;
}

.is-embedded .conversation-item {
  display: grid;
  align-items: center;
  min-height: 43px;
  margin: -1px 0 0;
  padding: 0 10px 0 12px;
  border: 1px solid #ececee;
  border-radius: 0;
  color: #56565d;
  background: #ffffff;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.is-embedded .conversation-item:first-of-type {
  margin-top: 0;
  border-radius: 8px 8px 0 0;
}

.is-embedded .conversation-item:last-of-type {
  border-radius: 0 0 8px 8px;
}

.is-embedded .conversation-item:only-of-type {
  border-radius: 8px;
}

.is-embedded .conversation-item:hover,
.is-embedded .conversation-item.active {
  position: relative;
  z-index: 1;
  border-color: #ddd9ff;
  background: #faf9ff;
  box-shadow: none;
}

.is-embedded .conversation-copy strong {
  color: #66666d;
  font-size: 11px;
  font-weight: 450;
}

.conversation-more {
  color: #9999a0;
  font-size: 15px;
  line-height: 1;
}

.is-embedded .conversation-empty {
  margin-top: 56px;
}

.is-embedded .message-panel {
  background: #ffffff;
}

.is-embedded .message-header {
  min-height: 62px;
  padding: 8px 10px 8px 8px;
}

.is-embedded .message-header > div:first-child {
  min-width: 0;
}

.is-embedded .title-row {
  min-width: 0;
  gap: 2px;
}

.is-embedded .history-back {
  width: 32px;
  min-width: 32px;
  height: 32px;
  padding: 0;
  color: #707077;
}

.is-embedded .title-row strong {
  max-width: 180px;
  font-size: 12px;
  font-weight: 600;
}

.is-embedded .title-row :deep(.ant-tag),
.is-embedded .message-header > div:first-child > span {
  display: none;
}

.is-embedded .header-actions :deep(.ant-btn) {
  width: 30px;
  min-width: 30px;
  height: 30px;
  padding: 0;
  color: #8b8b92;
  font-size: 12px;
}

.is-embedded .message-scroller {
  padding: 22px 18px 14px;
}

.is-embedded .message-row {
  grid-template-columns: 27px minmax(0, 1fr);
  gap: 9px;
  margin-bottom: 22px;
}

.is-embedded .message-avatar {
  width: 27px;
  height: 27px;
  border-radius: 8px;
  font-size: 11px;
}

.is-embedded .is-assistant .message-avatar,
.is-embedded .welcome-icon {
  color: #8178ff;
  background: #f1efff;
}

.is-embedded .message-meta {
  margin: 2px 0 7px;
}

.is-embedded .message-meta strong {
  font-size: 10px;
}

.is-embedded .user-question {
  padding: 9px 11px;
  border-radius: 3px 11px 11px;
  background: #f3f3f5;
  font-size: 12px;
  line-height: 1.6;
}

.is-embedded .answer-section-label,
.is-embedded .message-sources > span {
  font-size: 8px;
}

.is-embedded .welcome-state {
  width: auto;
  margin: 14vh 18px 0;
}

.is-embedded .welcome-icon {
  width: 48px;
  height: 48px;
  border-color: #e7e3ff;
  border-radius: 14px;
  box-shadow: none;
  font-size: 20px;
}

.is-embedded .welcome-state > span {
  color: #8178ff;
  font-size: 8px;
}

.is-embedded .welcome-state h2 {
  margin-top: 9px;
  font-family: inherit;
  font-size: 20px;
}

.is-embedded .welcome-state p {
  max-width: 280px;
  font-size: 11px;
  line-height: 1.7;
}

.is-embedded .composer {
  padding: 10px 13px 11px;
}

.is-embedded .composer-box {
  padding: 10px 9px 8px 12px;
  border-color: #dedee2;
  border-radius: 12px;
  box-shadow: 0 6px 22px rgb(24 24 27 / 6%);
}

.is-embedded .composer-box:focus-within {
  border-color: #cfcaff;
  box-shadow: 0 7px 24px rgb(86 75 210 / 10%);
}

.is-embedded .composer-box :deep(textarea) {
  font-size: 12px;
}

.is-embedded .composer-actions :deep(.ant-btn-primary) {
  border-color: #8178ff;
  background: #8178ff;
}

.is-embedded .answer-boundary {
  font-size: 8px;
}

@keyframes thinking {
  0%,
  60%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }

  30% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

@media (max-width: 1050px) {
  .chat-workspace {
    grid-template-columns: 230px minmax(0, 1fr);
  }

  .message-scroller,
  .composer {
    padding-inline: 24px;
  }
}

@media (max-width: 760px) {
  .chat-workspace {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 720px;
    max-height: none;
    overflow: visible;
  }

  .conversation-panel {
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }

  .conversation-list {
    grid-auto-columns: minmax(220px, 78vw);
    grid-auto-flow: column;
    max-height: none;
    overflow-x: auto;
    overflow-y: hidden;
  }

  .conversation-empty {
    margin: 18px 0;
  }

  .message-panel {
    min-height: 650px;
  }

  .message-scroller {
    min-height: 400px;
  }

  .chat-heading {
    align-items: flex-start;
  }
}
</style>
