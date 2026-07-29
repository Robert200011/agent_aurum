<script setup lang="ts">
import {
  DeleteOutlined,
  EditOutlined,
  FolderOpenOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { apiErrorMessage } from '@/services/http'
import { ragApi } from '@/services/rag'
import type { Project, ProjectInput, ProjectStatus } from '@/types/rag'
import { formatDate } from '@/utils/format'

const loading = ref(false)
const saving = ref(false)
const modalOpen = ref(false)
const projects = ref<Project[]>([])
const editing = ref<Project | null>(null)
const form = reactive<ProjectInput & { status: ProjectStatus }>({
  name: '',
  description: '',
  status: 'active',
})

const activeCount = computed(
  () => projects.value.filter((item) => item.status === 'active').length,
)
const disabledCount = computed(() => projects.value.length - activeCount.value)

const columns = [
  { title: '项目', key: 'project', minWidth: 240 },
  { title: '状态', key: 'status', width: 110 },
  { title: '更新时间', key: 'updated_at', width: 150 },
  { title: '操作', key: 'actions', width: 180, fixed: 'right' as const },
]

async function loadProjects(): Promise<void> {
  loading.value = true
  try {
    projects.value = (await ragApi.listProjects()).items
  } catch (error) {
    message.error(apiErrorMessage(error, '项目列表加载失败'))
  } finally {
    loading.value = false
  }
}

function resetForm(): void {
  Object.assign(form, {
    name: '',
    description: '',
    status: 'active' as ProjectStatus,
  })
}

function openCreate(): void {
  editing.value = null
  resetForm()
  modalOpen.value = true
}

function openEdit(project: Project): void {
  editing.value = project
  Object.assign(form, {
    name: project.name,
    description: project.description ?? '',
    status: project.status,
  })
  modalOpen.value = true
}

async function saveProject(): Promise<void> {
  if (!form.name.trim()) {
    message.warning('请输入项目名称')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await ragApi.updateProject(editing.value.id, {
        name: form.name.trim(),
        description: form.description?.trim() || null,
        status: form.status,
      })
      message.success('项目已更新')
    } else {
      await ragApi.createProject({
        name: form.name.trim(),
        description: form.description?.trim() || null,
      })
      message.success('项目已创建')
    }
    modalOpen.value = false
    await loadProjects()
  } catch (error) {
    message.error(apiErrorMessage(error, '项目保存失败'))
  } finally {
    saving.value = false
  }
}

function deleteProject(project: Project): void {
  Modal.confirm({
    title: `删除“${project.name}”？`,
    content:
      '项目将被软删除。如果它是某个知识库唯一的有效作用域，后端会拒绝删除，请先为知识库绑定其他有效项目。',
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await ragApi.deleteProject(project.id)
        message.success('项目已删除')
        await loadProjects()
      } catch (error) {
        message.error(apiErrorMessage(error, '项目删除失败'))
      }
    },
  })
}

onMounted(loadProjects)
</script>

<template>
  <div class="page-shell">
    <div class="page-heading">
      <div>
        <h1>Agent 项目</h1>
        <p>
          管理知识库的有效作用域。每个知识库始终需要归属于至少一个正常项目。
        </p>
      </div>
      <a-button type="primary" size="large" @click="openCreate">
        <PlusOutlined />新建项目
      </a-button>
    </div>

    <section class="project-summary">
      <article>
        <div class="summary-icon"><FolderOpenOutlined /></div>
        <div>
          <span>项目总数</span><strong>{{ projects.length }}</strong>
        </div>
      </article>
      <article>
        <div class="summary-icon active"><SafetyCertificateOutlined /></div>
        <div>
          <span>正常项目</span><strong>{{ activeCount }}</strong>
        </div>
      </article>
      <article>
        <div class="summary-icon disabled"><StopOutlined /></div>
        <div>
          <span>已停用</span><strong>{{ disabledCount }}</strong>
        </div>
      </article>
    </section>

    <a-card class="surface-card table-card" :bordered="false">
      <div class="table-toolbar">
        <div>
          <strong>项目列表</strong>
          <span>创建知识库时必须选择一个正常项目作为初始作用域</span>
        </div>
        <a-button @click="loadProjects">刷新</a-button>
      </div>
      <a-table
        :columns="columns"
        :data-source="projects"
        :loading="loading"
        :pagination="false"
        :scroll="{ x: 760 }"
        row-key="id"
      >
        <template
          #bodyCell="{
            column,
            record,
          }: {
            column: { key: string }
            record: Project
          }"
        >
          <template v-if="column.key === 'project'">
            <div class="project-cell">
              <div><FolderOpenOutlined /></div>
              <span>
                <strong>{{ record.name }}</strong>
                <small>{{ record.description || '暂无项目说明' }}</small>
              </span>
            </div>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.status === 'active' ? 'green' : 'default'">
              {{ record.status === 'active' ? '正常' : '已停用' }}
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
                @click="openEdit(record)"
              >
                <EditOutlined />编辑
              </a-button>
              <a-button
                type="link"
                danger
                class="table-action"
                @click="deleteProject(record)"
              >
                <DeleteOutlined />删除
              </a-button>
            </a-space>
          </template>
        </template>
        <template #emptyText>
          <a-empty description="还没有 Agent 项目">
            <a-button type="primary" @click="openCreate">
              创建第一个项目
            </a-button>
          </a-empty>
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="modalOpen"
      :title="editing ? '编辑项目' : '新建项目'"
      :confirm-loading="saving"
      ok-text="保存项目"
      cancel-text="取消"
      @ok="saveProject"
    >
      <a-form layout="vertical" :model="form">
        <a-form-item label="项目名称" required>
          <a-input
            v-model:value="form.name"
            :maxlength="128"
            placeholder="例如：个人财务顾问"
          />
        </a-form-item>
        <a-form-item label="项目说明">
          <a-textarea
            v-model:value="form.description"
            :maxlength="10000"
            :rows="4"
            show-count
            placeholder="说明项目服务对象和知识范围"
          />
        </a-form-item>
        <a-form-item v-if="editing" label="项目状态">
          <a-segmented
            v-model:value="form.status"
            :options="[
              { label: '正常', value: 'active' },
              { label: '停用', value: 'disabled' },
            ]"
          />
        </a-form-item>
        <a-alert
          v-if="editing && form.status === 'disabled'"
          type="warning"
          show-icon
          message="停用前请确认知识库仍有其他有效项目作用域"
          description="若该项目是任一知识库唯一的有效绑定，后端会拒绝本次操作。"
        />
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.project-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.project-summary article {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 92px;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: white;
}

.summary-icon,
.project-cell > div {
  display: grid;
  width: 42px;
  height: 42px;
  border-radius: 13px;
  color: #987122;
  background: #fbf2dd;
  font-size: 18px;
  place-items: center;
}

.summary-icon.active {
  color: var(--mint-700);
  background: var(--mint-100);
}

.summary-icon.disabled {
  color: var(--ink-500);
  background: #edf1ef;
}

.project-summary article > div:last-child {
  display: grid;
}

.project-summary span,
.table-toolbar span {
  color: var(--ink-500);
  font-size: 11px;
}

.project-summary strong {
  color: var(--ink-950);
  font-family: 'Iowan Old Style', Georgia, serif;
  font-size: 24px;
}

.table-card {
  overflow: hidden;
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 20px;
}

.table-toolbar > div,
.project-cell > span {
  display: grid;
}

.table-toolbar strong {
  color: var(--ink-950);
  font-size: 16px;
}

.project-cell {
  display: flex;
  align-items: center;
  gap: 11px;
  max-width: 580px;
}

.project-cell > div {
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  border-radius: 11px;
  font-size: 15px;
}

.project-cell strong {
  color: var(--ink-900);
  font-size: 13px;
}

.project-cell small {
  overflow: hidden;
  color: var(--ink-500);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 720px) {
  .project-summary {
    grid-template-columns: 1fr;
  }
}
</style>
