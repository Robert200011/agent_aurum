<script setup lang="ts">
import {
  CloudUploadOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { apiErrorMessage } from '@/services/http'
import { ragApi } from '@/services/rag'
import type {
  Document,
  DocumentVersion,
  IngestionJob,
  KnowledgeBase,
  RetrievalResponse,
} from '@/types/rag'

const loading = ref(true)
const detailLoading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const retrieving = ref(false)
const knowledgeBases = ref<KnowledgeBase[]>([])
const selectedKnowledgeBaseId = ref<string>()
const documents = ref<Document[]>([])
const selectedDocumentId = ref<string>()
const versions = ref<DocumentVersion[]>([])
const jobs = ref<IngestionJob[]>([])
const uploadFile = ref<File>()
const retrievalQuery = ref('')
const retrievalResult = ref<RetrievalResponse>()
const modalOpen = ref(false)
const editing = ref<KnowledgeBase>()
const form = reactive({ name: '', description: '' })

const selectedKnowledgeBase = computed(() =>
  knowledgeBases.value.find((item) => item.id === selectedKnowledgeBaseId.value),
)
const selectedDocument = computed(() =>
  documents.value.find((item) => item.id === selectedDocumentId.value),
)

function idempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
}

async function loadKnowledgeBases(): Promise<void> {
  loading.value = true
  try {
    knowledgeBases.value = (await ragApi.listKnowledgeBases()).items
    if (!knowledgeBases.value.some((item) => item.id === selectedKnowledgeBaseId.value)) {
      selectedKnowledgeBaseId.value = knowledgeBases.value[0]?.id
    }
  } catch (error) {
    message.error(apiErrorMessage(error, '个人知识库加载失败'))
  } finally {
    loading.value = false
  }
}

async function loadDocuments(): Promise<void> {
  const knowledgeBaseId = selectedKnowledgeBaseId.value
  documents.value = []
  versions.value = []
  jobs.value = []
  selectedDocumentId.value = undefined
  retrievalResult.value = undefined
  if (!knowledgeBaseId) return
  detailLoading.value = true
  try {
    documents.value = (await ragApi.listDocuments(knowledgeBaseId)).items
  } catch (error) {
    message.error(apiErrorMessage(error, '文档列表加载失败'))
  } finally {
    detailLoading.value = false
  }
}

async function selectDocument(document: Document): Promise<void> {
  selectedDocumentId.value = document.id
  try {
    const [versionList, jobList] = await Promise.all([
      ragApi.listDocumentVersions(document.id),
      ragApi.listIngestionJobs(document.id),
    ])
    versions.value = versionList.items
    jobs.value = jobList.items
  } catch (error) {
    message.error(apiErrorMessage(error, '文档处理记录加载失败'))
  }
}

function openCreate(): void {
  editing.value = undefined
  form.name = ''
  form.description = ''
  modalOpen.value = true
}

function openEdit(): void {
  if (!selectedKnowledgeBase.value) return
  editing.value = selectedKnowledgeBase.value
  form.name = editing.value.name
  form.description = editing.value.description ?? ''
  modalOpen.value = true
}

async function saveKnowledgeBase(): Promise<void> {
  if (!form.name.trim()) {
    message.warning('请输入知识库名称')
    return
  }
  saving.value = true
  try {
    const payload = { name: form.name.trim(), description: form.description.trim() || null }
    const saved = editing.value
      ? await ragApi.updateKnowledgeBase(editing.value.id, payload)
      : await ragApi.createKnowledgeBase(payload)
    modalOpen.value = false
    await loadKnowledgeBases()
    selectedKnowledgeBaseId.value = saved.id
    message.success(editing.value ? '知识库已更新' : '个人知识库已创建')
  } catch (error) {
    message.error(apiErrorMessage(error, '知识库保存失败'))
  } finally {
    saving.value = false
  }
}

async function toggleKnowledgeBaseStatus(): Promise<void> {
  const knowledgeBase = selectedKnowledgeBase.value
  if (!knowledgeBase) return
  try {
    if (knowledgeBase.status === 'active') {
      await ragApi.disableKnowledgeBase(knowledgeBase.id)
    } else {
      await ragApi.enableKnowledgeBase(knowledgeBase.id)
    }
    await loadKnowledgeBases()
    message.success(knowledgeBase.status === 'active' ? '知识库已停用' : '知识库已启用')
  } catch (error) {
    message.error(apiErrorMessage(error, '知识库状态更新失败'))
  }
}

function removeKnowledgeBase(): void {
  const knowledgeBase = selectedKnowledgeBase.value
  if (!knowledgeBase) return
  Modal.confirm({
    title: `删除“${knowledgeBase.name}”？`,
    content: '知识库将不再参与问答检索，已有历史引用仍会保留。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await ragApi.deleteKnowledgeBase(knowledgeBase.id)
      selectedKnowledgeBaseId.value = undefined
      await loadKnowledgeBases()
      message.success('知识库已删除')
    },
  })
}

function chooseFile(event: Event): void {
  uploadFile.value = (event.target as HTMLInputElement).files?.[0]
}

async function uploadDocument(): Promise<void> {
  const knowledgeBase = selectedKnowledgeBase.value
  if (!knowledgeBase || !uploadFile.value) {
    message.warning('请先选择文件')
    return
  }
  uploading.value = true
  try {
    await ragApi.uploadDocument(
      knowledgeBase.id,
      uploadFile.value,
      {},
      idempotencyKey(),
    )
    uploadFile.value = undefined
    await loadDocuments()
    message.success('文件已上传，后台正在建立索引')
  } catch (error) {
    message.error(apiErrorMessage(error, '文件上传失败'))
  } finally {
    uploading.value = false
  }
}

async function retryJob(job: IngestionJob): Promise<void> {
  try {
    await ragApi.retryIngestionJob(job.id)
    if (selectedDocument.value) await selectDocument(selectedDocument.value)
    message.success('处理任务已重新提交')
  } catch (error) {
    message.error(apiErrorMessage(error, '任务重试失败'))
  }
}

async function retrieve(): Promise<void> {
  const knowledgeBase = selectedKnowledgeBase.value
  if (!knowledgeBase || !retrievalQuery.value.trim()) return
  retrieving.value = true
  try {
    retrievalResult.value = await ragApi.retrieve(knowledgeBase.id, {
      query: retrievalQuery.value.trim(),
      limit: 8,
    })
  } catch (error) {
    message.error(apiErrorMessage(error, '检索预览失败'))
  } finally {
    retrieving.value = false
  }
}

watch(selectedKnowledgeBaseId, () => void loadDocuments())
onMounted(() => void loadKnowledgeBases())
</script>

<template>
  <div class="knowledge-page">
    <div class="page-heading">
      <div>
        <span class="heading-kicker">PERSONAL KNOWLEDGE</span>
        <h1>个人知识库</h1>
        <p>你可以独立维护自己的资料；智能问答只会在问题确实需要时检索这些内容。</p>
      </div>
      <a-button type="primary" size="large" @click="openCreate">
        <PlusOutlined />新建知识库
      </a-button>
    </div>

    <section class="knowledge-layout">
      <aside class="surface-card knowledge-list">
        <div class="panel-title"><DatabaseOutlined /><strong>我的知识库</strong></div>
        <a-spin :spinning="loading">
          <button
            v-for="item in knowledgeBases"
            :key="item.id"
            type="button"
            :class="{ selected: item.id === selectedKnowledgeBaseId }"
            @click="selectedKnowledgeBaseId = item.id"
          >
            <strong>{{ item.name }}</strong>
            <small>{{ item.description || '暂无说明' }}</small>
            <a-tag :color="item.status === 'active' ? 'green' : 'default'">
              {{ item.status === 'active' ? '已启用' : '已停用' }}
            </a-tag>
          </button>
          <a-empty v-if="!loading && !knowledgeBases.length" description="还没有个人知识库" />
        </a-spin>
      </aside>

      <main class="surface-card knowledge-detail">
        <a-empty v-if="!selectedKnowledgeBase" description="请选择或创建一个知识库" />
        <template v-else>
          <header class="detail-header">
            <div>
              <h2>{{ selectedKnowledgeBase.name }}</h2>
              <p>{{ selectedKnowledgeBase.description || '暂无知识库说明' }}</p>
            </div>
            <a-space wrap>
              <a-button @click="openEdit"><EditOutlined />编辑</a-button>
              <a-button @click="toggleKnowledgeBaseStatus">
                {{ selectedKnowledgeBase.status === 'active' ? '停用' : '启用' }}
              </a-button>
              <a-button danger type="text" @click="removeKnowledgeBase">
                <DeleteOutlined />删除
              </a-button>
            </a-space>
          </header>

          <a-alert
            v-if="selectedKnowledgeBase.status !== 'active'"
            type="warning"
            show-icon
            message="当前知识库已停用，不会参与智能问答检索"
          />

          <a-tabs>
            <a-tab-pane key="documents" tab="文档管理">
              <div class="upload-row">
                <input type="file" @change="chooseFile" />
                <a-button
                  type="primary"
                  :loading="uploading"
                  :disabled="selectedKnowledgeBase.status !== 'active'"
                  @click="uploadDocument"
                >
                  <CloudUploadOutlined />上传并建立索引
                </a-button>
                <a-button :loading="detailLoading" @click="loadDocuments">
                  <ReloadOutlined />刷新
                </a-button>
              </div>

              <div class="document-grid">
                <section class="document-list">
                  <button
                    v-for="document in documents"
                    :key="document.id"
                    type="button"
                    :class="{ selected: document.id === selectedDocumentId }"
                    @click="selectDocument(document)"
                  >
                    <FileTextOutlined />
                    <span><strong>{{ document.name }}</strong><small>{{ document.status }}</small></span>
                  </button>
                  <a-empty v-if="!documents.length" description="还没有上传文档" />
                </section>

                <section class="document-history">
                  <template v-if="selectedDocument">
                    <h3>{{ selectedDocument.name }}</h3>
                    <a-descriptions size="small" :column="1" bordered>
                      <a-descriptions-item label="文档状态">{{ selectedDocument.status }}</a-descriptions-item>
                      <a-descriptions-item label="文件类型">{{ selectedDocument.mime_type }}</a-descriptions-item>
                      <a-descriptions-item label="文件大小">{{ selectedDocument.size_bytes }} bytes</a-descriptions-item>
                    </a-descriptions>
                    <h4>版本</h4>
                    <a-list size="small" :data-source="versions">
                      <template #renderItem="{ item }">
                        <a-list-item>v{{ item.version }} · {{ item.status }}</a-list-item>
                      </template>
                    </a-list>
                    <h4>处理任务</h4>
                    <a-list size="small" :data-source="jobs">
                      <template #renderItem="{ item }">
                        <a-list-item>
                          {{ item.status }} · {{ item.progress }}%
                          <a-button v-if="item.status === 'failed'" type="link" @click="retryJob(item)">
                            重试
                          </a-button>
                        </a-list-item>
                      </template>
                    </a-list>
                  </template>
                  <a-empty v-else description="选择文档查看版本和处理状态" />
                </section>
              </div>
            </a-tab-pane>

            <a-tab-pane key="retrieval" tab="检索预览">
              <div class="retrieval-row">
                <a-input-search
                  v-model:value="retrievalQuery"
                  placeholder="输入问题，验证当前知识库能否找到相关内容"
                  enter-button="检索"
                  :loading="retrieving"
                  @search="retrieve"
                >
                  <template #prefix><SearchOutlined /></template>
                </a-input-search>
              </div>
              <a-list v-if="retrievalResult" :data-source="retrievalResult.items" bordered>
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a-list-item-meta :title="`${item.title} · ${item.score.toFixed(3)}`">
                      <template #description>{{ item.content }}</template>
                    </a-list-item-meta>
                  </a-list-item>
                </template>
              </a-list>
            </a-tab-pane>
          </a-tabs>
        </template>
      </main>
    </section>

    <a-modal
      v-model:open="modalOpen"
      :title="editing ? '编辑个人知识库' : '新建个人知识库'"
      ok-text="保存"
      cancel-text="取消"
      :confirm-loading="saving"
      @ok="saveKnowledgeBase"
    >
      <a-form layout="vertical">
        <a-form-item label="知识库名称" required>
          <a-input v-model:value="form.name" :maxlength="128" />
        </a-form-item>
        <a-form-item label="说明">
          <a-textarea v-model:value="form.description" :maxlength="10000" :rows="4" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.knowledge-page { display: grid; gap: 22px; }
.heading-kicker { color: var(--primary); font-size: 11px; font-weight: 800; letter-spacing: .16em; }
.knowledge-layout { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 18px; min-height: 650px; }
.knowledge-list, .knowledge-detail { padding: 20px; }
.panel-title { display: flex; gap: 9px; align-items: center; margin-bottom: 16px; }
.knowledge-list button, .document-list button { width: 100%; border: 1px solid transparent; border-radius: 12px; background: transparent; text-align: left; cursor: pointer; }
.knowledge-list button { display: grid; gap: 6px; padding: 13px; margin-bottom: 8px; }
.knowledge-list button small { color: var(--ink-500); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.knowledge-list button.selected, .document-list button.selected { border-color: rgb(47 111 237 / 25%); background: rgb(47 111 237 / 7%); }
.detail-header { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.detail-header h2, .detail-header p { margin: 0 0 6px; }
.upload-row, .retrieval-row { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
.document-grid { display: grid; grid-template-columns: minmax(220px, .8fr) minmax(320px, 1.4fr); gap: 18px; }
.document-list, .document-history { min-height: 330px; padding: 14px; border: 1px solid var(--line); border-radius: 14px; }
.document-list button { display: flex; align-items: center; gap: 10px; padding: 11px; margin-bottom: 7px; }
.document-list button span { display: grid; gap: 3px; min-width: 0; }
.document-list small { color: var(--ink-500); }
.document-history h4 { margin: 18px 0 7px; }
@media (max-width: 900px) { .knowledge-layout, .document-grid { grid-template-columns: 1fr; } }
</style>
