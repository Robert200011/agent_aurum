<script setup lang="ts">
import {
  CheckCircleOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DisconnectOutlined,
  DownloadOutlined,
  EditOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  LinkOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { apiErrorMessage } from '@/services/http'
import { ragApi } from '@/services/rag'
import type {
  Document,
  DocumentVersion,
  IngestionJob,
  KnowledgeBase,
  KnowledgeBaseStatus,
  Project,
  ProjectKnowledgeBaseBinding,
  RetrievedChunk,
  RetrievalResponse,
} from '@/types/rag'
import { formatDate } from '@/utils/format'

const ACCEPTED_DOCUMENTS = '.pdf,.docx,.md,.txt,.csv,.xlsx'
const ACTIVE_JOB_STATUSES = new Set(['awaiting_pipeline', 'processing'])

const loading = ref(false)
const workspaceLoading = ref(false)
const saving = ref(false)
const actionLoading = ref(false)
const uploading = ref(false)
const detailLoading = ref(false)
const retryingJobId = ref<string>()
const projects = ref<Project[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const documents = ref<Document[]>([])
const bindings = ref<ProjectKnowledgeBaseBinding[]>([])
const selectedKnowledgeBaseId = ref('')
const searchText = ref('')
const activeTab = ref('overview')

const knowledgeBaseModalOpen = ref(false)
const editingKnowledgeBase = ref<KnowledgeBase | null>(null)
const knowledgeBaseForm = reactive({
  name: '',
  description: '',
  project_id: '',
})

const bindingProjectId = ref<string>()

const uploadModalOpen = ref(false)
const uploadTarget = ref<Document | null>(null)
const uploadFile = ref<File | null>(null)
const uploadMetadata = ref('{}')
const uploadIdempotencyKey = ref('')

const detailDrawerOpen = ref(false)
const detailDocument = ref<Document | null>(null)
const documentVersions = ref<DocumentVersion[]>([])
const ingestionJobs = ref<IngestionJob[]>([])
let pollTimer: number | undefined

const retrieving = ref(false)
const retrievalError = ref('')
const retrievalResult = ref<RetrievalResponse | null>(null)
const retrievalForm = reactive({
  query: '',
  limit: 10,
  min_score: null as number | null,
})

const selectedKnowledgeBase = computed(
  () =>
    knowledgeBases.value.find(
      (item) => item.id === selectedKnowledgeBaseId.value,
    ) ?? null,
)
const projectMap = computed(
  () => new Map(projects.value.map((item) => [item.id, item])),
)
const filteredKnowledgeBases = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  if (!keyword) return knowledgeBases.value
  return knowledgeBases.value.filter(
    (item) =>
      item.name.toLowerCase().includes(keyword) ||
      item.description?.toLowerCase().includes(keyword),
  )
})
const publishedCount = computed(
  () =>
    knowledgeBases.value.filter((item) => item.status === 'published').length,
)
const processingDocumentCount = computed(
  () =>
    documents.value.filter(
      (item) => item.status === 'uploaded' && item.is_enabled,
    ).length,
)
const boundProjects = computed(() =>
  bindings.value.map((item) => ({
    binding: item,
    project: projectMap.value.get(item.project_id),
  })),
)
const availableBindingProjects = computed(() => {
  const boundIds = new Set(bindings.value.map((item) => item.project_id))
  return projects.value.filter(
    (item) => item.status === 'active' && !boundIds.has(item.id),
  )
})
const activeProjects = computed(() =>
  projects.value.filter((item) => item.status === 'active'),
)
const jobsByVersion = computed(() => {
  const result = new Map<string, IngestionJob>()
  for (const job of ingestionJobs.value) {
    if (!result.has(job.document_version_id))
      result.set(job.document_version_id, job)
  }
  return result
})

const documentColumns = [
  { title: '文档', key: 'document', minWidth: 260 },
  { title: '大小 / 类型', key: 'file', width: 155 },
  { title: '状态', key: 'status', width: 120 },
  { title: '更新时间', key: 'updated_at', width: 150 },
  { title: '操作', key: 'actions', width: 250, fixed: 'right' as const },
]

const knowledgeBaseStatusLabels: Record<KnowledgeBaseStatus, string> = {
  draft: '草稿',
  published: '已发布',
  disabled: '已停用',
}

const statusLabels: Record<string, string> = {
  uploaded: '等待入库',
  uploading: '上传中',
  awaiting_pipeline: '等待处理',
  processing: '处理中',
  published: '已发布',
  superseded: '历史版本',
  completed: '已完成',
  failed: '失败',
  disabled: '已停用',
  deleted: '已删除',
}

function statusColor(status: string): string {
  if (status === 'published' || status === 'completed') return 'green'
  if (status === 'processing') return 'blue'
  if (
    status === 'awaiting_pipeline' ||
    status === 'uploaded' ||
    status === 'uploading'
  )
    return 'gold'
  if (status === 'failed') return 'red'
  return 'gray'
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`
  return `${(value / 1024 ** 2).toFixed(1)} MiB`
}

function shortHash(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-6)}`
}

function resultLocation(item: RetrievedChunk): string {
  const parts: string[] = []
  if (item.page_number !== null) parts.push(`第 ${item.page_number} 页`)
  if (item.section_path) parts.push(item.section_path)
  if (item.sheet_name) parts.push(`工作表 ${item.sheet_name}`)
  if (item.row_start !== null) {
    parts.push(
      item.row_end !== null && item.row_end !== item.row_start
        ? `第 ${item.row_start}–${item.row_end} 行`
        : `第 ${item.row_start} 行`,
    )
  }
  return parts.join(' · ') || '文本片段'
}

async function loadInitialData(): Promise<void> {
  loading.value = true
  try {
    const [projectResult, knowledgeBaseResult] = await Promise.all([
      ragApi.listProjects(),
      ragApi.listKnowledgeBases(),
    ])
    projects.value = projectResult.items
    knowledgeBases.value = knowledgeBaseResult.items
    if (
      !selectedKnowledgeBaseId.value ||
      !knowledgeBases.value.some(
        (item) => item.id === selectedKnowledgeBaseId.value,
      )
    ) {
      selectedKnowledgeBaseId.value = knowledgeBases.value[0]?.id ?? ''
    }
  } catch (error) {
    message.error(apiErrorMessage(error, '知识库工作台加载失败'))
  } finally {
    loading.value = false
  }
}

async function loadWorkspace(knowledgeBaseId: string): Promise<void> {
  stopPolling()
  documents.value = []
  bindings.value = []
  retrievalResult.value = null
  retrievalError.value = ''
  if (!knowledgeBaseId) return
  workspaceLoading.value = true
  try {
    const [documentResult, bindingResult] = await Promise.all([
      ragApi.listDocuments(knowledgeBaseId),
      ragApi.listKnowledgeBaseProjects(knowledgeBaseId),
    ])
    if (selectedKnowledgeBaseId.value !== knowledgeBaseId) return
    documents.value = documentResult.items
    bindings.value = bindingResult
  } catch (error) {
    message.error(apiErrorMessage(error, '知识库详情加载失败'))
  } finally {
    if (selectedKnowledgeBaseId.value === knowledgeBaseId)
      workspaceLoading.value = false
  }
}

function selectKnowledgeBase(knowledgeBaseId: string): void {
  selectedKnowledgeBaseId.value = knowledgeBaseId
  activeTab.value = 'overview'
}

function openCreateKnowledgeBase(): void {
  if (!activeProjects.value.length) {
    message.warning('请先创建或启用一个 Agent 项目')
    return
  }
  editingKnowledgeBase.value = null
  Object.assign(knowledgeBaseForm, {
    name: '',
    description: '',
    project_id: activeProjects.value[0]?.id ?? '',
  })
  knowledgeBaseModalOpen.value = true
}

function openEditKnowledgeBase(): void {
  const knowledgeBase = selectedKnowledgeBase.value
  if (!knowledgeBase) return
  editingKnowledgeBase.value = knowledgeBase
  Object.assign(knowledgeBaseForm, {
    name: knowledgeBase.name,
    description: knowledgeBase.description ?? '',
    project_id: '',
  })
  knowledgeBaseModalOpen.value = true
}

async function saveKnowledgeBase(): Promise<void> {
  if (!knowledgeBaseForm.name.trim()) {
    message.warning('请输入知识库名称')
    return
  }
  if (!editingKnowledgeBase.value && !knowledgeBaseForm.project_id) {
    message.warning('请选择初始项目')
    return
  }
  saving.value = true
  try {
    let saved: KnowledgeBase
    if (editingKnowledgeBase.value) {
      saved = await ragApi.updateKnowledgeBase(editingKnowledgeBase.value.id, {
        name: knowledgeBaseForm.name.trim(),
        description: knowledgeBaseForm.description.trim() || null,
      })
      message.success('知识库信息已更新')
    } else {
      saved = await ragApi.createKnowledgeBase({
        project_id: knowledgeBaseForm.project_id,
        name: knowledgeBaseForm.name.trim(),
        description: knowledgeBaseForm.description.trim() || null,
      })
      message.success('知识库已创建')
    }
    knowledgeBaseModalOpen.value = false
    await loadInitialData()
    selectedKnowledgeBaseId.value = saved.id
  } catch (error) {
    message.error(apiErrorMessage(error, '知识库保存失败'))
  } finally {
    saving.value = false
  }
}

async function runKnowledgeBaseAction(
  action: 'publish' | 'disable',
): Promise<void> {
  const knowledgeBase = selectedKnowledgeBase.value
  if (!knowledgeBase) return
  actionLoading.value = true
  try {
    const updated =
      action === 'publish'
        ? await ragApi.publishKnowledgeBase(knowledgeBase.id)
        : await ragApi.disableKnowledgeBase(knowledgeBase.id)
    const index = knowledgeBases.value.findIndex(
      (item) => item.id === updated.id,
    )
    if (index >= 0) knowledgeBases.value[index] = updated
    message.success(action === 'publish' ? '知识库已发布' : '知识库已停用')
  } catch (error) {
    message.error(
      apiErrorMessage(
        error,
        action === 'publish' ? '知识库发布失败' : '知识库停用失败',
      ),
    )
  } finally {
    actionLoading.value = false
  }
}

function confirmKnowledgeBaseAction(action: 'publish' | 'disable'): void {
  const knowledgeBase = selectedKnowledgeBase.value
  if (!knowledgeBase) return
  Modal.confirm({
    title:
      action === 'publish'
        ? `发布“${knowledgeBase.name}”？`
        : `停用“${knowledgeBase.name}”？`,
    content:
      action === 'publish'
        ? '发布后，已成功入库且启用的文档可参与后续检索。'
        : '停用是终止性操作：该知识库将不能继续发布、绑定项目、上传文档或执行检索。',
    okText: action === 'publish' ? '确认发布' : '确认停用',
    okType: action === 'disable' ? 'danger' : 'primary',
    cancelText: '取消',
    onOk: () => runKnowledgeBaseAction(action),
  })
}

function deleteKnowledgeBase(): void {
  const knowledgeBase = selectedKnowledgeBase.value
  if (!knowledgeBase) return
  Modal.confirm({
    title: `删除“${knowledgeBase.name}”？`,
    content: '知识库会被软删除并从管理列表隐藏。此操作不用于临时停用。',
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await ragApi.deleteKnowledgeBase(knowledgeBase.id)
        message.success('知识库已删除')
        selectedKnowledgeBaseId.value = ''
        await loadInitialData()
      } catch (error) {
        message.error(apiErrorMessage(error, '知识库删除失败'))
      }
    },
  })
}

async function bindProject(): Promise<void> {
  const knowledgeBase = selectedKnowledgeBase.value
  if (!knowledgeBase || !bindingProjectId.value) {
    message.warning('请选择需要绑定的项目')
    return
  }
  actionLoading.value = true
  try {
    await ragApi.bindKnowledgeBase(knowledgeBase.id, bindingProjectId.value)
    message.success('项目已绑定')
    bindingProjectId.value = undefined
    bindings.value = await ragApi.listKnowledgeBaseProjects(knowledgeBase.id)
  } catch (error) {
    message.error(apiErrorMessage(error, '项目绑定失败'))
  } finally {
    actionLoading.value = false
  }
}

function canUnbind(projectId: string): boolean {
  return bindings.value.some(
    (item) =>
      item.project_id !== projectId &&
      projectMap.value.get(item.project_id)?.status === 'active',
  )
}

async function unbindProject(projectId: string): Promise<void> {
  const knowledgeBase = selectedKnowledgeBase.value
  if (!knowledgeBase) return
  try {
    await ragApi.unbindKnowledgeBase(knowledgeBase.id, projectId)
    message.success('项目绑定已移除')
    bindings.value = await ragApi.listKnowledgeBaseProjects(knowledgeBase.id)
  } catch (error) {
    message.error(apiErrorMessage(error, '移除绑定失败'))
  }
}

function parseMetadata(): Record<string, string> | null {
  const value = uploadMetadata.value.trim()
  if (!value) return {}
  try {
    const parsed: unknown = JSON.parse(value)
    if (
      typeof parsed !== 'object' ||
      parsed === null ||
      Array.isArray(parsed) ||
      Object.entries(parsed).some(
        ([key, item]) => !key || typeof item !== 'string',
      )
    ) {
      throw new Error('invalid metadata')
    }
    return parsed as Record<string, string>
  } catch {
    message.warning('元数据必须是仅包含字符串键和值的 JSON 对象')
    return null
  }
}

function openUpload(document: Document | null = null): void {
  uploadTarget.value = document
  uploadFile.value = null
  uploadMetadata.value = '{}'
  uploadIdempotencyKey.value = crypto.randomUUID()
  uploadModalOpen.value = true
}

function selectUploadFile(event: Event): void {
  const input = event.target as HTMLInputElement
  uploadFile.value = input.files?.[0] ?? null
}

async function upload(): Promise<void> {
  const knowledgeBase = selectedKnowledgeBase.value
  const metadata = parseMetadata()
  if (!knowledgeBase || !uploadFile.value || metadata === null) {
    if (!uploadFile.value) message.warning('请选择要上传的文档')
    return
  }
  uploading.value = true
  try {
    const result = uploadTarget.value
      ? await ragApi.uploadDocumentVersion(
          uploadTarget.value.id,
          uploadFile.value,
          metadata,
          uploadIdempotencyKey.value,
        )
      : await ragApi.uploadDocument(
          knowledgeBase.id,
          uploadFile.value,
          metadata,
          uploadIdempotencyKey.value,
        )
    uploadModalOpen.value = false
    message.success(uploadTarget.value ? '新版本已提交入库' : '文档已提交入库')
    await loadWorkspace(knowledgeBase.id)
    await openDocumentDetails(result.document)
  } catch (error) {
    message.error(apiErrorMessage(error, '文档上传失败'))
  } finally {
    uploading.value = false
  }
}

async function loadDocumentDetails(silent = false): Promise<void> {
  const document = detailDocument.value
  if (!document) return
  if (!silent) detailLoading.value = true
  try {
    const [versionResult, jobResult] = await Promise.all([
      ragApi.listDocumentVersions(document.id),
      ragApi.listIngestionJobs(document.id),
    ])
    documentVersions.value = versionResult.items
    ingestionJobs.value = jobResult.items
    if (jobResult.items.some((item) => ACTIVE_JOB_STATUSES.has(item.status))) {
      startPolling()
    } else {
      stopPolling()
    }
    if (silent && selectedKnowledgeBaseId.value) {
      documents.value = (
        await ragApi.listDocuments(selectedKnowledgeBaseId.value)
      ).items
      detailDocument.value =
        documents.value.find((item) => item.id === document.id) ??
        detailDocument.value
    }
  } catch (error) {
    if (!silent) message.error(apiErrorMessage(error, '版本与任务信息加载失败'))
  } finally {
    if (!silent) detailLoading.value = false
  }
}

async function openDocumentDetails(document: Document): Promise<void> {
  detailDocument.value = document
  detailDrawerOpen.value = true
  documentVersions.value = []
  ingestionJobs.value = []
  await loadDocumentDetails()
}

function startPolling(): void {
  if (pollTimer !== undefined) return
  pollTimer = window.setInterval(() => void loadDocumentDetails(true), 3000)
}

function stopPolling(): void {
  if (pollTimer === undefined) return
  window.clearInterval(pollTimer)
  pollTimer = undefined
}

function closeDetailDrawer(): void {
  stopPolling()
  detailDrawerOpen.value = false
}

async function retryJob(job: IngestionJob): Promise<void> {
  retryingJobId.value = job.id
  try {
    await ragApi.retryIngestionJob(job.id)
    message.success('入库任务已重新提交')
    await loadDocumentDetails()
  } catch (error) {
    message.error(apiErrorMessage(error, '任务重试失败'))
  } finally {
    retryingJobId.value = undefined
  }
}

async function retryDispatch(job: IngestionJob): Promise<void> {
  retryingJobId.value = job.id
  try {
    await ragApi.retryIngestionDispatch(job.id)
    message.success('任务投递事件已重新进入待发送队列')
    startPolling()
  } catch (error) {
    message.error(
      apiErrorMessage(
        error,
        '只有投递事件已失败且任务仍在等待处理时，才能重新投递',
      ),
    )
  } finally {
    retryingJobId.value = undefined
  }
}

async function downloadVersion(version: DocumentVersion): Promise<void> {
  try {
    const result = await ragApi.getDownloadUrl(version.id)
    window.open(result.url, '_blank', 'noopener,noreferrer')
  } catch (error) {
    message.error(apiErrorMessage(error, '下载地址生成失败'))
  }
}

function disableDocument(document: Document): void {
  Modal.confirm({
    title: `停用“${document.name}”？`,
    content: '停用后该文档不再参与检索，也不能上传新版本或重试失败任务。',
    okText: '确认停用',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await ragApi.disableDocument(document.id)
        message.success('文档已停用')
        if (selectedKnowledgeBaseId.value)
          await loadWorkspace(selectedKnowledgeBaseId.value)
      } catch (error) {
        message.error(apiErrorMessage(error, '文档停用失败'))
      }
    },
  })
}

function deleteDocument(document: Document): void {
  Modal.confirm({
    title: `删除“${document.name}”？`,
    content: '文档会被软删除并退出检索范围，已有版本记录仍保留用于审计。',
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await ragApi.deleteDocument(document.id)
        message.success('文档已删除')
        if (selectedKnowledgeBaseId.value)
          await loadWorkspace(selectedKnowledgeBaseId.value)
      } catch (error) {
        message.error(apiErrorMessage(error, '文档删除失败'))
      }
    },
  })
}

async function retrieve(): Promise<void> {
  const knowledgeBase = selectedKnowledgeBase.value
  if (!knowledgeBase || !retrievalForm.query.trim()) {
    message.warning('请输入检索问题')
    return
  }
  retrieving.value = true
  retrievalError.value = ''
  retrievalResult.value = null
  try {
    retrievalResult.value = await ragApi.retrieve(knowledgeBase.id, {
      query: retrievalForm.query.trim(),
      limit: retrievalForm.limit,
      min_score: retrievalForm.min_score,
    })
  } catch (error) {
    retrievalError.value = apiErrorMessage(error, '检索测试失败')
  } finally {
    retrieving.value = false
  }
}

watch(selectedKnowledgeBaseId, (value) => void loadWorkspace(value))
watch(detailDrawerOpen, (open) => {
  if (!open) stopPolling()
})

onMounted(loadInitialData)
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="page-shell">
    <div class="page-heading">
      <div>
        <h1>知识库工作台</h1>
        <p>
          从项目作用域到文档入库、版本追踪和 Dense
          检索，在同一处完成管理与验证。
        </p>
      </div>
      <a-button type="primary" size="large" @click="openCreateKnowledgeBase">
        <PlusOutlined />新建知识库
      </a-button>
    </div>

    <section class="knowledge-summary">
      <article>
        <DatabaseOutlined />
        <div>
          <span>知识库</span><strong>{{ knowledgeBases.length }}</strong>
        </div>
      </article>
      <article>
        <CheckCircleOutlined />
        <div>
          <span>已发布</span><strong>{{ publishedCount }}</strong>
        </div>
      </article>
      <article>
        <FileTextOutlined />
        <div>
          <span>当前文档</span><strong>{{ documents.length }}</strong>
        </div>
      </article>
      <article>
        <ReloadOutlined />
        <div>
          <span>等待入库</span><strong>{{ processingDocumentCount }}</strong>
        </div>
      </article>
    </section>

    <div class="knowledge-workbench">
      <a-card
        class="surface-card knowledge-nav"
        :bordered="false"
        :loading="loading"
      >
        <a-input
          v-model:value="searchText"
          allow-clear
          placeholder="搜索知识库"
        >
          <template #prefix><SearchOutlined /></template>
        </a-input>
        <div class="knowledge-list">
          <button
            v-for="knowledgeBase in filteredKnowledgeBases"
            :key="knowledgeBase.id"
            type="button"
            :class="{ selected: knowledgeBase.id === selectedKnowledgeBaseId }"
            @click="selectKnowledgeBase(knowledgeBase.id)"
          >
            <span class="knowledge-icon"><DatabaseOutlined /></span>
            <span class="knowledge-copy">
              <strong>{{ knowledgeBase.name }}</strong>
              <small>{{ knowledgeBase.description || '暂无说明' }}</small>
            </span>
            <a-badge
              :status="
                knowledgeBase.status === 'published'
                  ? 'success'
                  : knowledgeBase.status === 'draft'
                    ? 'warning'
                    : 'default'
              "
            />
          </button>
          <a-empty
            v-if="!filteredKnowledgeBases.length"
            :description="
              knowledgeBases.length ? '没有匹配的知识库' : '还没有知识库'
            "
            :image-style="{ height: '52px' }"
          />
        </div>
      </a-card>

      <a-card
        class="surface-card knowledge-detail"
        :bordered="false"
        :loading="workspaceLoading"
      >
        <a-empty
          v-if="!selectedKnowledgeBase"
          description="请选择或创建一个知识库"
        />
        <template v-else>
          <div class="detail-heading">
            <div>
              <div class="detail-title-row">
                <h2>{{ selectedKnowledgeBase.name }}</h2>
                <a-tag :color="statusColor(selectedKnowledgeBase.status)">
                  {{ knowledgeBaseStatusLabels[selectedKnowledgeBase.status] }}
                </a-tag>
              </div>
              <p>{{ selectedKnowledgeBase.description || '暂无知识库说明' }}</p>
            </div>
            <a-space wrap>
              <a-button @click="openEditKnowledgeBase">
                <EditOutlined />编辑
              </a-button>
              <a-button
                v-if="selectedKnowledgeBase.status === 'draft'"
                type="primary"
                :loading="actionLoading"
                @click="confirmKnowledgeBaseAction('publish')"
              >
                <CheckCircleOutlined />发布
              </a-button>
              <a-button
                v-if="selectedKnowledgeBase.status !== 'disabled'"
                danger
                :loading="actionLoading"
                @click="confirmKnowledgeBaseAction('disable')"
              >
                <StopOutlined />停用
              </a-button>
              <a-button danger type="text" @click="deleteKnowledgeBase">
                <DeleteOutlined />
              </a-button>
            </a-space>
          </div>

          <a-tabs v-model:active-key="activeTab" class="detail-tabs">
            <a-tab-pane key="overview" tab="概览与项目">
              <div class="overview-grid">
                <section class="info-panel">
                  <div class="section-heading">
                    <div>
                      <strong>索引配置</strong><span>创建时固化，保证版本检索一致</span>
                    </div>
                  </div>
                  <a-descriptions :column="1" size="small">
                    <a-descriptions-item label="Embedding">
                      {{ selectedKnowledgeBase.embedding_provider }} /
                      {{ selectedKnowledgeBase.embedding_model }}
                    </a-descriptions-item>
                    <a-descriptions-item label="向量配置">
                      {{ selectedKnowledgeBase.embedding_dimensions }} 维 ·
                      {{ selectedKnowledgeBase.embedding_distance_metric }}
                    </a-descriptions-item>
                    <a-descriptions-item label="流水线版本">
                      {{ selectedKnowledgeBase.pipeline_version }}
                    </a-descriptions-item>
                    <a-descriptions-item label="发布时间">
                      {{
                        formatDate(
                          selectedKnowledgeBase.published_at,
                          'YYYY-MM-DD HH:mm',
                        )
                      }}
                    </a-descriptions-item>
                    <a-descriptions-item label="最近更新">
                      {{
                        formatDate(
                          selectedKnowledgeBase.updated_at,
                          'YYYY-MM-DD HH:mm',
                        )
                      }}
                    </a-descriptions-item>
                  </a-descriptions>
                </section>

                <section class="info-panel">
                  <div class="section-heading">
                    <div>
                      <strong>项目作用域</strong><span>至少保留一个正常项目</span>
                    </div>
                  </div>
                  <div class="binding-list">
                    <div
                      v-for="item in boundProjects"
                      :key="item.binding.project_id"
                    >
                      <span>
                        <FolderOpenOutlined />
                        <span>
                          <strong>{{
                            item.project?.name ?? '未知项目'
                          }}</strong>
                          <small>{{
                            item.project?.status === 'active'
                              ? '正常'
                              : '已停用'
                          }}</small>
                        </span>
                      </span>
                      <a-tooltip
                        :title="
                          canUnbind(item.binding.project_id)
                            ? '移除项目绑定'
                            : '知识库必须保留至少一个正常项目'
                        "
                      >
                        <a-button
                          type="text"
                          danger
                          :disabled="!canUnbind(item.binding.project_id)"
                          @click="unbindProject(item.binding.project_id)"
                        >
                          <DisconnectOutlined />
                        </a-button>
                      </a-tooltip>
                    </div>
                  </div>
                  <div
                    v-if="
                      selectedKnowledgeBase.status !== 'disabled' &&
                        availableBindingProjects.length
                    "
                    class="binding-form"
                  >
                    <a-select
                      v-model:value="bindingProjectId"
                      allow-clear
                      placeholder="选择正常项目"
                    >
                      <a-select-option
                        v-for="project in availableBindingProjects"
                        :key="project.id"
                        :value="project.id"
                      >
                        {{ project.name }}
                      </a-select-option>
                    </a-select>
                    <a-button :loading="actionLoading" @click="bindProject">
                      <LinkOutlined />绑定
                    </a-button>
                  </div>
                </section>
              </div>
            </a-tab-pane>

            <a-tab-pane key="documents">
              <template #tab>
                文档与任务
                <a-badge :count="documents.length" :overflow-count="999" />
              </template>
              <div class="documents-toolbar">
                <div>
                  <strong>知识文档</strong>
                  <span>PDF、DOCX、Markdown、TXT、CSV、XLSX，单文件最大 50
                    MiB</span>
                </div>
                <a-button
                  type="primary"
                  :disabled="selectedKnowledgeBase.status === 'disabled'"
                  @click="openUpload()"
                >
                  <CloudUploadOutlined />上传文档
                </a-button>
              </div>
              <a-alert
                v-if="selectedKnowledgeBase.status === 'disabled'"
                type="warning"
                show-icon
                message="已停用的知识库不能再上传或处理文档"
                class="section-alert"
              />
              <a-table
                :columns="documentColumns"
                :data-source="documents"
                :pagination="false"
                :scroll="{ x: 960 }"
                row-key="id"
                size="middle"
              >
                <template
                  #bodyCell="{
                    column,
                    record,
                  }: {
                    column: { key: string }
                    record: Document
                  }"
                >
                  <template v-if="column.key === 'document'">
                    <div class="document-cell">
                      <div><FileTextOutlined /></div>
                      <span>
                        <strong>{{ record.name }}</strong>
                        <small :title="record.content_hash">
                          SHA-256 {{ shortHash(record.content_hash) }}
                        </small>
                      </span>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'file'">
                    <span class="file-meta">{{
                      formatBytes(record.size_bytes)
                    }}</span>
                    <small class="file-meta">{{ record.mime_type }}</small>
                  </template>
                  <template v-else-if="column.key === 'status'">
                    <a-tag :color="statusColor(record.status)">
                      {{ statusLabels[record.status] ?? record.status }}
                    </a-tag>
                  </template>
                  <template v-else-if="column.key === 'updated_at'">
                    <span class="muted">{{
                      formatDate(record.updated_at, 'YYYY-MM-DD HH:mm')
                    }}</span>
                  </template>
                  <template v-else-if="column.key === 'actions'">
                    <a-space>
                      <a-button
                        type="link"
                        class="table-action"
                        @click="openDocumentDetails(record)"
                      >
                        <HistoryOutlined />版本与任务
                      </a-button>
                      <a-dropdown>
                        <a-button type="link" class="table-action">
                          更多
                        </a-button>
                        <template #overlay>
                          <a-menu>
                            <a-menu-item
                              key="version"
                              :disabled="
                                !record.is_enabled ||
                                  selectedKnowledgeBase.status === 'disabled'
                              "
                              @click="openUpload(record)"
                            >
                              <CloudUploadOutlined />上传新版本
                            </a-menu-item>
                            <a-menu-item
                              key="disable"
                              danger
                              :disabled="!record.is_enabled"
                              @click="disableDocument(record)"
                            >
                              <StopOutlined />停用文档
                            </a-menu-item>
                            <a-menu-divider />
                            <a-menu-item
                              key="delete"
                              danger
                              @click="deleteDocument(record)"
                            >
                              <DeleteOutlined />删除文档
                            </a-menu-item>
                          </a-menu>
                        </template>
                      </a-dropdown>
                    </a-space>
                  </template>
                </template>
                <template #emptyText>
                  <a-empty description="还没有文档">
                    <a-button
                      type="primary"
                      :disabled="selectedKnowledgeBase.status === 'disabled'"
                      @click="openUpload()"
                    >
                      上传第一份文档
                    </a-button>
                  </a-empty>
                </template>
              </a-table>
            </a-tab-pane>

            <a-tab-pane key="retrieval" tab="检索测试">
              <div class="retrieval-layout">
                <section class="retrieval-console">
                  <div class="section-heading">
                    <div>
                      <strong>Dense 检索</strong><span>直接调用当前知识库的检索 API</span>
                    </div>
                  </div>
                  <a-alert
                    v-if="selectedKnowledgeBase.status !== 'published'"
                    type="warning"
                    show-icon
                    message="只有已发布知识库可以执行检索"
                    class="section-alert"
                  />
                  <a-form layout="vertical">
                    <a-form-item label="测试问题" required>
                      <a-textarea
                        v-model:value="retrievalForm.query"
                        :rows="5"
                        :maxlength="2000"
                        show-count
                        placeholder="例如：资产配置中如何控制单一行业暴露？"
                        @press-enter.ctrl="retrieve"
                      />
                    </a-form-item>
                    <div class="retrieval-options">
                      <a-form-item label="返回条数">
                        <a-input-number
                          v-model:value="retrievalForm.limit"
                          :min="1"
                          :max="50"
                          style="width: 100%"
                        />
                      </a-form-item>
                      <a-form-item label="最低相似度（可选）">
                        <a-input-number
                          v-model:value="retrievalForm.min_score"
                          :min="-1"
                          :max="1"
                          :step="0.05"
                          style="width: 100%"
                          placeholder="不限制"
                        />
                      </a-form-item>
                    </div>
                    <a-button
                      type="primary"
                      block
                      size="large"
                      :loading="retrieving"
                      :disabled="selectedKnowledgeBase.status !== 'published'"
                      @click="retrieve"
                    >
                      <FileSearchOutlined />执行检索
                    </a-button>
                  </a-form>
                  <p class="retrieval-hint">
                    检索需要生成 query Embedding；本地未配置真实 DashScope Key
                    时，后端会返回可控的 503，而不会影响其他管理功能。
                  </p>
                </section>

                <section class="retrieval-results">
                  <a-alert
                    v-if="retrievalError"
                    type="error"
                    show-icon
                    :message="retrievalError"
                    closable
                    @close="retrievalError = ''"
                  />
                  <template v-if="retrievalResult">
                    <div class="result-summary">
                      <div>
                        <strong>{{ retrievalResult.items.length }} 个结果</strong>
                        <span>
                          {{ retrievalResult.latency_ms }} ms ·
                          {{ retrievalResult.embedding_model }}
                        </span>
                      </div>
                      <a-tag color="cyan">Dense / cosine</a-tag>
                    </div>
                    <article
                      v-for="(item, index) in retrievalResult.items"
                      :key="item.chunk_id"
                      class="chunk-card"
                    >
                      <header>
                        <div>
                          <span class="result-index">{{ index + 1 }}</span>
                          <span>
                            <strong>{{ item.title }}</strong>
                            <small>{{ resultLocation(item) }}</small>
                          </span>
                        </div>
                        <a-tag color="green">{{ item.score.toFixed(4) }}</a-tag>
                      </header>
                      <p>{{ item.content }}</p>
                      <footer>
                        <span>chunk {{ item.chunk_id }}</span>
                        <span>{{ item.retrieval_source }}</span>
                      </footer>
                    </article>
                    <a-empty
                      v-if="!retrievalResult.items.length"
                      description="当前阈值下没有匹配片段"
                    />
                  </template>
                  <div
                    v-else-if="!retrievalError"
                    class="retrieval-placeholder"
                  >
                    <FileSearchOutlined />
                    <strong>等待检索</strong>
                    <span>结果将展示来源文档、页码或行范围、Chunk
                      正文和相似度分数。</span>
                  </div>
                </section>
              </div>
            </a-tab-pane>
          </a-tabs>
        </template>
      </a-card>
    </div>

    <a-modal
      v-model:open="knowledgeBaseModalOpen"
      :title="editingKnowledgeBase ? '编辑知识库' : '新建知识库'"
      :confirm-loading="saving"
      ok-text="保存知识库"
      cancel-text="取消"
      @ok="saveKnowledgeBase"
    >
      <a-form layout="vertical" :model="knowledgeBaseForm">
        <a-form-item v-if="!editingKnowledgeBase" label="初始项目" required>
          <a-select
            v-model:value="knowledgeBaseForm.project_id"
            placeholder="选择正常项目"
          >
            <a-select-option
              v-for="project in activeProjects"
              :key="project.id"
              :value="project.id"
            >
              {{ project.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="知识库名称" required>
          <a-input
            v-model:value="knowledgeBaseForm.name"
            :maxlength="128"
            placeholder="例如：投资研究方法"
          />
        </a-form-item>
        <a-form-item label="知识库说明">
          <a-textarea
            v-model:value="knowledgeBaseForm.description"
            :rows="4"
            :maxlength="10000"
            show-count
            placeholder="说明内容范围、维护方式和适用场景"
          />
        </a-form-item>
        <a-alert
          v-if="!editingKnowledgeBase"
          type="info"
          show-icon
          message="Embedding 配置由后端统一固化"
          description="当前使用 DashScope text-embedding-v4、1024 维向量和 cosine 距离。"
        />
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="uploadModalOpen"
      :title="
        uploadTarget ? `上传“${uploadTarget.name}”的新版本` : '上传知识文档'
      "
      :confirm-loading="uploading"
      ok-text="提交入库"
      cancel-text="取消"
      @ok="upload"
    >
      <div class="upload-panel">
        <a-alert
          type="info"
          show-icon
          message="上传成功只代表任务已受理"
          description="文档会异步经过解析、分块、Embedding 和原子发布，请在版本与任务面板查看进度。"
        />
        <a-form layout="vertical">
          <a-form-item label="文档文件" required>
            <label class="document-picker">
              <CloudUploadOutlined />
              <span>
                <strong>{{ uploadFile?.name ?? '选择文档' }}</strong>
                <small>PDF / DOCX / MD / TXT / CSV / XLSX，最大 50 MiB</small>
              </span>
              <input
                type="file"
                :accept="ACCEPTED_DOCUMENTS"
                @change="selectUploadFile"
              />
            </label>
          </a-form-item>
          <a-form-item label="版本元数据（可选 JSON）">
            <a-textarea
              v-model:value="uploadMetadata"
              :rows="4"
              placeholder="{&quot;category&quot;:&quot;投资研究&quot;,&quot;source&quot;:&quot;内部资料&quot;}"
            />
            <p class="field-help">最多 16 项，键和值都必须是字符串。</p>
          </a-form-item>
        </a-form>
      </div>
    </a-modal>

    <a-drawer
      v-model:open="detailDrawerOpen"
      :width="720"
      title="版本与入库任务"
      class="document-detail-drawer"
      @close="closeDetailDrawer"
    >
      <template v-if="detailDocument">
        <div class="drawer-document-heading">
          <div class="document-cell">
            <div><FileTextOutlined /></div>
            <span>
              <strong>{{ detailDocument.name }}</strong>
              <small>{{ formatBytes(detailDocument.size_bytes) }} ·
                {{ detailDocument.mime_type }}</small>
            </span>
          </div>
          <a-button
            :disabled="
              !detailDocument.is_enabled ||
                selectedKnowledgeBase?.status === 'disabled'
            "
            @click="openUpload(detailDocument)"
          >
            <CloudUploadOutlined />上传新版本
          </a-button>
        </div>

        <a-spin :spinning="detailLoading">
          <a-timeline class="version-timeline">
            <a-timeline-item
              v-for="version in documentVersions"
              :key="version.id"
              :color="statusColor(version.status)"
            >
              <article class="version-card">
                <header>
                  <div>
                    <strong>版本 {{ version.version }}</strong>
                    <a-tag :color="statusColor(version.status)">
                      {{ statusLabels[version.status] ?? version.status }}
                    </a-tag>
                  </div>
                  <a-button type="link" @click="downloadVersion(version)">
                    <DownloadOutlined />下载源文件
                  </a-button>
                </header>
                <div class="version-meta">
                  <span>{{
                    formatDate(version.created_at, 'YYYY-MM-DD HH:mm:ss')
                  }}</span>
                  <span>{{ version.pipeline_version }}</span>
                  <span :title="version.content_hash">SHA-256 {{ shortHash(version.content_hash) }}</span>
                </div>
                <div
                  v-if="Object.keys(version.metadata_json).length"
                  class="metadata-tags"
                >
                  <a-tag
                    v-for="(value, key) in version.metadata_json"
                    :key="key"
                  >
                    {{ key }}: {{ value }}
                  </a-tag>
                </div>

                <template
                  v-for="job in [jobsByVersion.get(version.id)]"
                  :key="job?.id ?? version.id"
                >
                  <section v-if="job" class="job-panel">
                    <div class="job-heading">
                      <span>
                        <strong>入库任务</strong>
                        <small>
                          {{ statusLabels[job.status] ?? job.status }} ·
                          自动重试 {{ job.retry_count }}/{{ job.max_retries }} ·
                          人工重试
                          {{ job.manual_retry_count }}
                        </small>
                      </span>
                      <a-space>
                        <a-button
                          v-if="job.status === 'failed'"
                          size="small"
                          :loading="retryingJobId === job.id"
                          @click="retryJob(job)"
                        >
                          <ReloadOutlined />重试入库
                        </a-button>
                        <a-tooltip
                          v-if="job.status === 'awaiting_pipeline'"
                          title="仅用于 Outbox 投递事件已经失败的情况；若事件仍正常，后端会拒绝操作"
                        >
                          <a-button
                            size="small"
                            :loading="retryingJobId === job.id"
                            @click="retryDispatch(job)"
                          >
                            重新投递
                          </a-button>
                        </a-tooltip>
                      </a-space>
                    </div>
                    <a-progress
                      :percent="job.progress"
                      :status="
                        job.status === 'failed' ? 'exception' : undefined
                      "
                      size="small"
                    />
                    <a-alert
                      v-if="job.error_message"
                      type="error"
                      show-icon
                      :message="job.error_code || '入库失败'"
                      :description="job.error_message"
                    />
                  </section>
                </template>
              </article>
            </a-timeline-item>
          </a-timeline>
          <a-empty v-if="!documentVersions.length" description="暂无版本记录" />
        </a-spin>
      </template>
    </a-drawer>
  </div>
</template>

<style scoped>
.knowledge-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.knowledge-summary article {
  display: flex;
  align-items: center;
  gap: 13px;
  min-height: 84px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: white;
}

.knowledge-summary article > .anticon {
  display: grid;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  color: var(--mint-700);
  background: var(--mint-100);
  font-size: 17px;
  place-items: center;
}

.knowledge-summary article:nth-child(even) > .anticon {
  color: #987122;
  background: #fbf2dd;
}

.knowledge-summary article > div {
  display: grid;
}

.knowledge-summary span {
  color: var(--ink-500);
  font-size: 10px;
}

.knowledge-summary strong {
  color: var(--ink-950);
  font-family: 'Iowan Old Style', Georgia, serif;
  font-size: 22px;
}

.knowledge-workbench {
  display: grid;
  grid-template-columns: 292px minmax(0, 1fr);
  align-items: start;
  gap: 18px;
}

.knowledge-nav {
  position: sticky;
  top: 102px;
}

.knowledge-list {
  display: grid;
  max-height: calc(100vh - 260px);
  margin-top: 14px;
  overflow: auto;
  gap: 5px;
}

.knowledge-list button {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 12px;
  border: 1px solid transparent;
  border-radius: 12px;
  color: var(--ink-800);
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.knowledge-list button:hover {
  background: #f3f7f4;
}

.knowledge-list button.selected {
  border-color: #bcded5;
  background: #edf8f4;
}

.knowledge-icon,
.document-cell > div {
  display: grid;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  color: var(--mint-700);
  background: var(--mint-100);
  place-items: center;
}

.knowledge-copy,
.document-cell > span {
  display: grid;
  min-width: 0;
}

.knowledge-copy strong {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-copy small {
  overflow: hidden;
  color: var(--ink-500);
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-detail {
  min-width: 0;
}

.detail-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.detail-title-row {
  display: flex;
  align-items: center;
  gap: 9px;
}

.detail-heading h2 {
  margin: 0;
  color: var(--ink-950);
  font-family: 'Iowan Old Style', 'Songti SC', serif;
  font-size: 25px;
}

.detail-heading p {
  max-width: 680px;
  margin: 5px 0 0;
  color: var(--ink-500);
  font-size: 12px;
}

.detail-tabs {
  margin-top: 14px;
}

.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
}

.info-panel,
.retrieval-console,
.retrieval-results {
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fbfcfa;
}

.section-heading,
.documents-toolbar,
.result-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-heading {
  margin-bottom: 16px;
}

.section-heading > div,
.documents-toolbar > div,
.result-summary > div {
  display: grid;
}

.section-heading strong,
.documents-toolbar strong,
.result-summary strong {
  color: var(--ink-950);
  font-size: 14px;
}

.section-heading span,
.documents-toolbar span,
.result-summary span {
  color: var(--ink-500);
  font-size: 10px;
}

.binding-list {
  display: grid;
  gap: 7px;
}

.binding-list > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 48px;
  padding: 7px 8px 7px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: white;
}

.binding-list > div > span {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--mint-700);
}

.binding-list > div > span > span {
  display: grid;
}

.binding-list strong {
  color: var(--ink-900);
  font-size: 11px;
}

.binding-list small {
  color: var(--ink-500);
  font-size: 9px;
}

.binding-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  margin-top: 12px;
}

.documents-toolbar {
  margin-bottom: 16px;
}

.section-alert {
  margin-bottom: 16px;
}

.document-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.document-cell > div {
  flex: 0 0 auto;
}

.document-cell strong {
  overflow: hidden;
  color: var(--ink-900);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-cell small,
.file-meta {
  display: block;
  overflow: hidden;
  color: var(--ink-500);
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.retrieval-layout {
  display: grid;
  grid-template-columns: minmax(280px, 0.75fr) minmax(360px, 1.25fr);
  align-items: start;
  gap: 16px;
}

.retrieval-options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.retrieval-hint,
.field-help {
  margin: 10px 0 0;
  color: var(--ink-500);
  font-size: 10px;
  line-height: 1.6;
}

.retrieval-results {
  display: grid;
  min-height: 430px;
  gap: 12px;
}

.chunk-card {
  padding: 15px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: white;
}

.chunk-card header,
.chunk-card header > div,
.chunk-card footer {
  display: flex;
  align-items: center;
}

.chunk-card header {
  justify-content: space-between;
  gap: 12px;
}

.chunk-card header > div {
  min-width: 0;
  gap: 9px;
}

.chunk-card header > div > span:last-child {
  display: grid;
  min-width: 0;
}

.result-index {
  display: grid;
  flex: 0 0 auto;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  color: white;
  background: var(--mint-700);
  font-size: 10px;
  font-weight: 700;
  place-items: center;
}

.chunk-card header strong {
  overflow: hidden;
  color: var(--ink-900);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chunk-card header small {
  color: var(--ink-500);
  font-size: 9px;
}

.chunk-card p {
  margin: 13px 0;
  color: var(--ink-700);
  font-size: 12px;
  line-height: 1.75;
  white-space: pre-wrap;
}

.chunk-card footer {
  justify-content: space-between;
  gap: 10px;
  color: var(--ink-500);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 8px;
}

.retrieval-placeholder {
  display: grid;
  align-content: center;
  justify-items: center;
  min-height: 360px;
  color: var(--ink-500);
  text-align: center;
}

.retrieval-placeholder > .anticon {
  margin-bottom: 12px;
  color: #a9bcb6;
  font-size: 38px;
}

.retrieval-placeholder strong {
  color: var(--ink-700);
  font-size: 13px;
}

.retrieval-placeholder span {
  max-width: 340px;
  margin-top: 6px;
  font-size: 10px;
  line-height: 1.6;
}

.upload-panel {
  display: grid;
  gap: 18px;
}

.document-picker {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 106px;
  padding: 20px;
  border: 1px dashed #9ebbb3;
  border-radius: 12px;
  color: var(--mint-700);
  background: #f4faf7;
  cursor: pointer;
  gap: 12px;
}

.document-picker > .anticon {
  font-size: 25px;
}

.document-picker > span {
  display: grid;
}

.document-picker strong {
  color: var(--ink-800);
  font-size: 12px;
}

.document-picker small {
  color: var(--ink-500);
  font-size: 9px;
}

.document-picker input {
  display: none;
}

.drawer-document-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 26px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: #f7faf8;
}

.version-card {
  margin: 0 0 16px 8px;
  padding: 15px;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: white;
}

.version-card > header,
.version-card > header > div,
.job-heading,
.job-heading > span {
  display: flex;
  align-items: center;
}

.version-card > header,
.job-heading {
  justify-content: space-between;
  gap: 10px;
}

.version-card > header > div {
  gap: 8px;
}

.version-card > header strong {
  color: var(--ink-950);
  font-size: 13px;
}

.version-meta {
  display: flex;
  flex-wrap: wrap;
  margin: 8px 0 11px;
  color: var(--ink-500);
  font-size: 9px;
  gap: 7px 14px;
}

.metadata-tags {
  margin-bottom: 10px;
}

.job-panel {
  margin-top: 12px;
  padding: 12px;
  border-radius: 10px;
  background: #f5f8f6;
}

.job-heading {
  margin-bottom: 8px;
}

.job-heading > span {
  align-items: flex-start;
  flex-direction: column;
}

.job-heading strong {
  color: var(--ink-800);
  font-size: 10px;
}

.job-heading small {
  color: var(--ink-500);
  font-size: 8px;
}

.job-panel .ant-alert {
  margin-top: 8px;
}

@media (max-width: 1180px) {
  .knowledge-summary {
    grid-template-columns: repeat(2, 1fr);
  }

  .knowledge-workbench {
    grid-template-columns: 240px minmax(0, 1fr);
  }

  .overview-grid,
  .retrieval-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 820px) {
  .knowledge-workbench {
    grid-template-columns: 1fr;
  }

  .knowledge-nav {
    position: static;
  }

  .knowledge-list {
    max-height: 250px;
  }

  .detail-heading,
  .documents-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media (max-width: 560px) {
  .knowledge-summary,
  .retrieval-options {
    grid-template-columns: 1fr;
  }

  .binding-form {
    grid-template-columns: 1fr;
  }
}
</style>
