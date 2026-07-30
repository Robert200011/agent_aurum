<script setup lang="ts">
import {
  EditOutlined,
  FileSearchOutlined,
  InboxOutlined,
  MessageOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SendOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import { computed, nextTick, onMounted, ref } from 'vue'

import AnswerContent from '@/components/chat/AnswerContent.vue'
import { chatApi } from '@/services/chat'
import { apiErrorMessage } from '@/services/http'
import type {
  ChatProject,
  Conversation,
  ConversationDetail,
  MessageCitation,
} from '@/types/chat'
import { citationLocation } from '@/utils/chat'

dayjs.extend(relativeTime)

const loading = ref(true)
const detailLoading = ref(false)
const saving = ref(false)
const sending = ref(false)
const projects = ref<ChatProject[]>([])
const conversations = ref<Conversation[]>([])
const activeConversation = ref<ConversationDetail | null>(null)
const question = ref('')
const pendingQuestion = ref('')
const errorText = ref('')
const messageScroller = ref<HTMLElement | null>(null)

const createOpen = ref(false)
const createProjectId = ref<string>()
const createTitle = ref('')
const renameOpen = ref(false)
const renameTitle = ref('')

const citationOpen = ref(false)
const selectedCitation = ref<MessageCitation | null>(null)

const activeProject = computed(() =>
  projects.value.find(
    (project) => project.id === activeConversation.value?.project_id,
  ),
)
const canAsk = computed(
  () =>
    activeConversation.value?.status === 'active' &&
    Boolean(question.value.trim()) &&
    !sending.value,
)

function projectName(projectId: string | null): string {
  return (
    projects.value.find((project) => project.id === projectId)?.name ??
    '项目不可用'
  )
}

async function loadWorkspace(): Promise<void> {
  loading.value = true
  try {
    const [projectList, conversationList] = await Promise.all([
      chatApi.listProjects(),
      chatApi.listConversations(),
    ])
    projects.value = projectList.items
    conversations.value = conversationList.items
    createProjectId.value ??= projects.value[0]?.id
    if (conversations.value[0]) {
      await selectConversation(conversations.value[0].id)
    }
  } catch (error) {
    message.error(apiErrorMessage(error, '问答工作台加载失败'))
  } finally {
    loading.value = false
  }
}

async function refreshConversations(): Promise<void> {
  conversations.value = (await chatApi.listConversations()).items
}

async function selectConversation(conversationId: string): Promise<void> {
  if (detailLoading.value) return
  detailLoading.value = true
  errorText.value = ''
  try {
    activeConversation.value = await chatApi.getConversation(conversationId)
    await scrollToBottom()
  } catch (error) {
    message.error(apiErrorMessage(error, '会话加载失败'))
  } finally {
    detailLoading.value = false
  }
}

function openCreate(): void {
  createProjectId.value ??= projects.value[0]?.id
  createTitle.value = ''
  createOpen.value = true
}

async function createConversation(): Promise<void> {
  if (!createProjectId.value) {
    message.warning('请选择一个可用项目')
    return
  }
  saving.value = true
  try {
    const created = await chatApi.createConversation(
      createProjectId.value,
      createTitle.value,
    )
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

async function submitQuestion(): Promise<void> {
  const conversation = activeConversation.value
  const normalized = question.value.trim()
  if (!conversation || !normalized || sending.value) return

  question.value = ''
  pendingQuestion.value = normalized
  errorText.value = ''
  sending.value = true
  await scrollToBottom()
  try {
    await chatApi.ask(conversation.id, normalized)
    await Promise.all([
      selectConversation(conversation.id),
      refreshConversations(),
    ])
  } catch (error) {
    errorText.value = apiErrorMessage(error, '回答生成失败，请稍后重试')
    question.value = normalized
    try {
      await selectConversation(conversation.id)
    } catch {
      // 原错误信息更有助于用户恢复，不用二次加载错误覆盖它。
    }
  } finally {
    pendingQuestion.value = ''
    sending.value = false
    await scrollToBottom()
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

onMounted(loadWorkspace)
</script>

<template>
  <div class="chat-page">
    <div class="page-heading chat-heading">
      <div>
        <span class="heading-kicker">PROJECT RAG</span>
        <h1>智能问答</h1>
        <p>回答只使用当前会话绑定项目的已发布知识，并保留可核验引用。</p>
      </div>
      <a-button
        type="primary"
        size="large"
        :disabled="projects.length === 0"
        @click="openCreate"
      >
        <PlusOutlined />新建会话
      </a-button>
    </div>

    <a-alert
      v-if="!loading && projects.length === 0"
      type="warning"
      show-icon
      message="暂无可问答项目"
      description="请联系管理员启用项目，并为其绑定至少一个已发布知识库。"
    />

    <section class="chat-workspace surface-card">
      <aside class="conversation-panel">
        <div class="panel-heading">
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

        <a-skeleton :loading="loading" active :paragraph="{ rows: 5 }">
          <div v-if="conversations.length" class="conversation-list">
            <button
              v-for="conversation in conversations"
              :key="conversation.id"
              type="button"
              :class="[
                'conversation-item',
                {
                  active: activeConversation?.id === conversation.id,
                  archived: conversation.status === 'archived',
                },
              ]"
              @click="selectConversation(conversation.id)"
            >
              <span class="conversation-icon"><MessageOutlined /></span>
              <span class="conversation-copy">
                <strong>{{ conversation.title }}</strong>
                <small>{{ projectName(conversation.project_id) }}</small>
                <time>{{ dayjs(conversation.updated_at).fromNow() }}</time>
              </span>
              <InboxOutlined
                v-if="conversation.status === 'archived'"
                class="archive-mark"
              />
            </button>
          </div>
          <a-empty
            v-else
            :image="undefined"
            description="还没有问答会话"
            class="conversation-empty"
          >
            <a-button
              type="link"
              :disabled="projects.length === 0"
              @click="openCreate"
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
                {{ activeProject?.name ?? '项目不可用' }}
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
                  @click="archiveConversation"
                >
                  <InboxOutlined />
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
              <span>已连接 {{ activeProject?.name ?? '当前项目' }}</span>
              <h2>从项目知识中寻找答案</h2>
              <p>
                可询问文档中的事实、规则或说明。回答后的引用编号可以点击核验。
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
                    chatMessage.status === 'failed' && !chatMessage.content
                  "
                  class="failed-answer"
                >
                  本次回答生成失败，可重新提交问题。
                </div>
                <AnswerContent
                  v-else-if="chatMessage.role === 'assistant'"
                  :answer="chatMessage.content"
                  :citation-ids="
                    chatMessage.citations.map((citation) => citation.citation_id)
                  "
                  @citation="
                    (citationId) =>
                      openCitation(chatMessage.citations, citationId)
                  "
                />
                <p v-else class="user-question">{{ chatMessage.content }}</p>
                <div
                  v-if="
                    chatMessage.role === 'assistant' &&
                      chatMessage.citations.length
                  "
                  class="message-sources"
                >
                  <span>参考来源</span>
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
              </div>
            </article>

            <template v-if="sending">
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
                  <div class="thinking-indicator">
                    <i /><i /><i />
                    <span>正在检索项目知识并生成回答…</span>
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
                placeholder="输入问题，例如：这份制度对费用报销有哪些要求？"
                @keydown="handleComposerKeydown"
              />
              <div class="composer-actions">
                <span>Ctrl / ⌘ + Enter 发送</span>
                <a-button
                  type="primary"
                  shape="circle"
                  size="large"
                  aria-label="发送问题"
                  :loading="sending"
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
          <p>每个会话固定绑定一个项目，避免不同知识范围相互污染。</p>
          <a-button
            type="primary"
            :disabled="projects.length === 0"
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
        <a-form-item label="项目" required>
          <a-select
            v-model:value="createProjectId"
            placeholder="选择知识范围"
            style="width: 100%"
          >
            <a-select-option
              v-for="project in projects"
              :key="project.id"
              :value="project.id"
            >
              {{ project.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
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
          message="项目在会话创建后不可更换"
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
  max-height: calc(100vh - 290px);
  padding: 12px;
  overflow-y: auto;
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
