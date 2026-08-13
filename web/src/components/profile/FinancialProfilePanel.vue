<script setup lang="ts">
import {
  ArrowLeftOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
} from "@ant-design/icons-vue";
import { message, Modal } from "ant-design-vue";
import { computed, onMounted, reactive, ref } from "vue";

import { apiErrorMessage } from "@/services/http";
import { settingsApi } from "@/services/settings";
import type {
  EmploymentStatus as ApiEmploymentStatus,
  PersonalFinancialProfile,
  PersonalFinancialProfileInput,
} from "@/types/api";

type EmploymentStatus = "" | ApiEmploymentStatus;
type MemoryCategory = "goal" | "preference" | "constraint" | "personal";

interface FinancialProfileDraft {
  birthDate: string;
  residenceProvince: string;
  residenceCity: string;
  employmentStatus: EmploymentStatus;
  occupation: string;
  annualIncome: string;
  annualExpenseBudget: string;
}

interface MemoryDraft {
  id: string;
  category: MemoryCategory;
  title: string;
  content: string;
  updatedAt: string;
}

const emit = defineEmits<{ back: [] }>();

const profile = reactive<FinancialProfileDraft>({
  birthDate: "",
  residenceProvince: "",
  residenceCity: "",
  employmentStatus: "",
  occupation: "",
  annualIncome: "",
  annualExpenseBudget: "",
});
const profileForm = reactive<FinancialProfileDraft>({ ...profile });
const profileEditorOpen = ref(false);
const profileLoading = ref(true);
const profileSaving = ref(false);
const profileLoadFailed = ref(false);
const profileExists = ref(false);
const profileCurrency = ref("CNY");
const memorySettingsOpen = ref(false);
const memoryListOpen = ref(false);
const memoryEditorOpen = ref(false);
const memoryEnabled = ref(true);
const memoryEnabledDraft = ref(true);
const editingMemoryId = ref<string | null>(null);
const memoryForm = reactive<Omit<MemoryDraft, "id" | "updatedAt">>({
  category: "goal",
  title: "",
  content: "",
});
const memories = ref<MemoryDraft[]>([
  {
    id: "demo-goal",
    category: "goal",
    title: "优先建立应急储备",
    content: "希望先建立覆盖 6 个月必要开支的应急资金，再考虑提高长期投资比例。",
    updatedAt: "刚刚",
  },
  {
    id: "demo-preference",
    category: "preference",
    title: "偏好稳健、清晰的建议",
    content: "讨论投资时优先说明风险、流动性和数据口径，不给出确定性买卖结论。",
    updatedAt: "今天",
  },
  {
    id: "demo-constraint",
    category: "constraint",
    title: "保留日常现金流",
    content: "制定预算时需要为日常生活与短期计划保留足够的可用现金。",
    updatedAt: "今天",
  },
]);

const employmentLabels: Record<EmploymentStatus, string> = {
  "": "待完善",
  employed: "在职",
  self_employed: "自由职业 / 个体经营",
  student: "学生",
  retired: "退休",
  other: "其他",
};
const categoryLabels: Record<MemoryCategory, string> = {
  goal: "财务目标",
  preference: "回答偏好",
  constraint: "财务约束",
  personal: "个人信息",
};

const latestMemory = computed(() => memories.value[0] ?? null);
const age = computed(() => {
  if (!profile.birthDate) return "待完善";
  const birth = new Date(`${profile.birthDate}T00:00:00`);
  if (Number.isNaN(birth.getTime())) return "待完善";
  const now = new Date();
  let years = now.getFullYear() - birth.getFullYear();
  const beforeBirthday =
    now.getMonth() < birth.getMonth() ||
    (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate());
  if (beforeBirthday) years -= 1;
  return years >= 0 ? `${years} 岁` : "待完善";
});
const residence = computed(() => {
  const parts = [profile.residenceProvince, profile.residenceCity].filter(Boolean);
  return parts.length ? parts.join(" · ") : "待完善";
});
const profileCompletion = computed(() => {
  const values = [
    profile.birthDate,
    profile.residenceProvince,
    profile.residenceCity,
    profile.employmentStatus,
    profile.occupation,
    profile.annualIncome,
    profile.annualExpenseBudget,
  ];
  return Math.round((values.filter(Boolean).length / values.length) * 100);
});

function displayDate(value: string): string {
  if (!value) return "待完善";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return "待完善";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(parsed);
}

function displayMoney(value: string): string {
  if (!value.trim()) return "待完善";
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) return "待完善";
  return `${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(amount)} 元`;
}

function openProfileEditor(): void {
  if (profileLoading.value || profileLoadFailed.value || profileSaving.value) return;
  Object.assign(profileForm, profile);
  profileEditorOpen.value = true;
}

function nullableText(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function nullableMoney(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function profilePayload(): PersonalFinancialProfileInput {
  return {
    birth_date: profileForm.birthDate || null,
    residence_province: nullableText(profileForm.residenceProvince),
    residence_city: nullableText(profileForm.residenceCity),
    employment_status: profileForm.employmentStatus || null,
    occupation: nullableText(profileForm.occupation),
    annual_income: nullableMoney(profileForm.annualIncome),
    annual_expense_budget: nullableMoney(profileForm.annualExpenseBudget),
    currency: profileCurrency.value,
  };
}

function applyServerProfile(value: PersonalFinancialProfile): void {
  profileCurrency.value = value.currency;
  Object.assign(profile, {
    birthDate: value.birth_date ?? "",
    residenceProvince: value.residence_province ?? "",
    residenceCity: value.residence_city ?? "",
    employmentStatus: value.employment_status ?? "",
    occupation: value.occupation ?? "",
    annualIncome: value.annual_income == null ? "" : String(value.annual_income),
    annualExpenseBudget:
      value.annual_expense_budget == null ? "" : String(value.annual_expense_budget),
  });
}

async function loadFinancialProfile(): Promise<void> {
  profileLoading.value = true;
  profileLoadFailed.value = false;
  try {
    const value = await settingsApi.financialProfile();
    profileExists.value = value !== null;
    if (value) applyServerProfile(value);
    else Object.assign(profile, {
      birthDate: "",
      residenceProvince: "",
      residenceCity: "",
      employmentStatus: "",
      occupation: "",
      annualIncome: "",
      annualExpenseBudget: "",
    });
  } catch (error) {
    profileLoadFailed.value = true;
    message.error(apiErrorMessage(error, "个人财务档案加载失败"));
  } finally {
    profileLoading.value = false;
  }
}

async function saveFinancialProfile(): Promise<void> {
  if (profileSaving.value) return;
  profileSaving.value = true;
  try {
    const payload = profilePayload();
    const saved = profileExists.value
      ? await settingsApi.updateFinancialProfile(payload)
      : await settingsApi.createFinancialProfile(payload);
    applyServerProfile(saved);
    profileExists.value = true;
    profileEditorOpen.value = false;
    message.success("个人财务档案已保存");
  } catch (error) {
    message.error(apiErrorMessage(error, "个人财务档案保存失败"));
  } finally {
    profileSaving.value = false;
  }
}

function openMemorySettings(): void {
  memoryEnabledDraft.value = memoryEnabled.value;
  memorySettingsOpen.value = true;
}

function saveMemorySettings(): void {
  memoryEnabled.value = memoryEnabledDraft.value;
  memorySettingsOpen.value = false;
  message.success(memoryEnabled.value ? "记忆功能预览已开启" : "记忆功能预览已关闭");
}

function openNewMemory(): void {
  editingMemoryId.value = null;
  Object.assign(memoryForm, { category: "goal", title: "", content: "" });
  memoryEditorOpen.value = true;
}

function openMemoryEditor(memory: MemoryDraft): void {
  editingMemoryId.value = memory.id;
  Object.assign(memoryForm, {
    category: memory.category,
    title: memory.title,
    content: memory.content,
  });
  memoryEditorOpen.value = true;
}

function saveMemoryPreview(): void {
  const title = memoryForm.title.trim();
  const content = memoryForm.content.trim();
  if (!title || !content) {
    message.warning("请填写记忆标题和内容");
    return;
  }
  const existing = memories.value.find((item) => item.id === editingMemoryId.value);
  if (existing) {
    Object.assign(existing, { ...memoryForm, title, content, updatedAt: "刚刚" });
  } else {
    memories.value.unshift({
      id: `preview-${Date.now()}`,
      ...memoryForm,
      title,
      content,
      updatedAt: "刚刚",
    });
  }
  memoryEditorOpen.value = false;
  message.success("记忆预览已更新，本阶段尚未同步到后端");
}

function deleteMemory(memory: MemoryDraft): void {
  Modal.confirm({
    title: "删除这条记忆？",
    content: "当前仅删除本次页面会话中的演示数据。",
    okText: "删除",
    cancelText: "取消",
    okType: "danger",
    onOk() {
      memories.value = memories.value.filter((item) => item.id !== memory.id);
    },
  });
}

onMounted(loadFinancialProfile);
</script>

<template>
  <section class="financial-profile" aria-label="个人财务档案">
    <header class="profile-header">
      <button type="button" class="icon-button" aria-label="返回会话列表" @click="emit('back')">
        <ArrowLeftOutlined />
      </button>
      <div>
        <span>PERSONAL FINANCE</span>
        <h2>个人财务档案</h2>
      </div>
      <span class="preview-badge">档案已接入</span>
    </header>

    <div class="profile-scroll">
      <a-alert
        type="warning"
        show-icon
        class="preview-alert"
        message="记忆功能仍为界面预览"
        description="个人财务档案现已保存到后端数据库；下方记忆内容仍只在本次页面会话中演示，尚未用于 Agent 回答。"
      />

      <section class="memory-card" :class="{ 'is-disabled': !memoryEnabled }">
        <div class="card-heading">
          <div>
            <span class="card-kicker">AI MEMORY</span>
            <strong>个性化记忆</strong>
          </div>
          <button
            type="button"
            class="icon-button subtle"
            aria-label="记忆设置"
            @click="openMemorySettings"
          >
            <SettingOutlined />
          </button>
        </div>

        <button type="button" class="memory-preview" @click="memoryListOpen = true">
          <span class="memory-status-dot" :class="{ active: memoryEnabled }" />
          <span class="memory-copy">
            <small>{{ memoryEnabled ? `已开启 · ${memories.length} 条记忆` : "记忆功能已关闭" }}</small>
            <strong>{{ latestMemory?.title ?? "尚未保存记忆" }}</strong>
            <span>{{ latestMemory?.content ?? "后续可在这里查看 Agent 能调用的长期记忆。" }}</span>
          </span>
          <RightOutlined />
        </button>
      </section>

      <section class="profile-card" :aria-busy="profileLoading">
        <div class="card-heading">
          <div>
            <span class="card-kicker">PROFILE</span>
            <strong>个人信息</strong>
          </div>
          <button
            type="button"
            class="icon-button subtle"
            aria-label="编辑个人信息"
            :disabled="profileLoading || profileLoadFailed || profileSaving"
            @click="openProfileEditor"
          >
            <EditOutlined />
          </button>
        </div>

        <div v-if="profileLoading" class="profile-state">
          <a-spin size="small" />
          <span>正在加载已保存的档案…</span>
        </div>

        <div v-else-if="profileLoadFailed" class="profile-state error">
          <span>档案加载失败，请检查网络后重试。</span>
          <a-button size="small" @click="loadFinancialProfile">重新加载</a-button>
        </div>

        <template v-else>
          <div class="completion-row">
            <span>档案完整度</span>
            <strong>{{ profileCompletion }}%</strong>
            <a-progress :percent="profileCompletion" :show-info="false" size="small" />
          </div>

          <dl class="profile-fields">
            <div>
              <dt>出生日期</dt>
              <dd>{{ displayDate(profile.birthDate) }}</dd>
            </div>
            <div>
              <dt>年龄</dt>
              <dd>{{ age }}</dd>
            </div>
            <div>
              <dt>居住省市</dt>
              <dd>{{ residence }}</dd>
            </div>
            <div>
              <dt>就业情况</dt>
              <dd>{{ employmentLabels[profile.employmentStatus] }}</dd>
            </div>
            <div>
              <dt>职业</dt>
              <dd>{{ profile.occupation || "待完善" }}</dd>
            </div>
            <div>
              <dt>申报年收入</dt>
              <dd>{{ displayMoney(profile.annualIncome) }}</dd>
            </div>
            <div>
              <dt>年度开销预算</dt>
              <dd>{{ displayMoney(profile.annualExpenseBudget) }}</dd>
            </div>
          </dl>
        </template>
      </section>

      <section class="live-data-note">
        <SafetyCertificateOutlined />
        <div>
          <strong>实时财务数据保持独立</strong>
          <span>账户余额、流水和持仓仍应由受控只读工具实时读取，不保存为长期记忆。</span>
        </div>
      </section>
    </div>

    <a-modal
      v-model:open="memorySettingsOpen"
      centered
      title="记忆设置"
      :width="420"
      ok-text="保存"
      cancel-text="取消"
      @ok="saveMemorySettings"
    >
      <div class="memory-settings">
        <div>
          <strong>开启记忆功能</strong>
          <span>未来开启后，Agent 会按当前问题检索相关记忆并生成更有针对性的回答。</span>
        </div>
        <div class="switch-row">
          <span>{{ memoryEnabledDraft ? "开" : "关" }}</span>
          <a-switch v-model:checked="memoryEnabledDraft" />
        </div>
        <a-alert
          type="warning"
          show-icon
          message="此开关目前仅控制界面预览"
          description="后端接入后，关闭状态将同时停止记忆召回和新记忆写入。"
        />
      </div>
    </a-modal>

    <a-modal
      v-model:open="profileEditorOpen"
      centered
      title="编辑个人信息"
      :width="520"
      ok-text="保存"
      cancel-text="取消"
      :confirm-loading="profileSaving"
      :mask-closable="!profileSaving"
      :keyboard="!profileSaving"
      @ok="saveFinancialProfile"
    >
      <a-form layout="vertical" class="profile-form">
        <div class="form-grid">
          <a-form-item label="出生日期">
            <a-input v-model:value="profileForm.birthDate" type="date" />
          </a-form-item>
          <a-form-item label="就业情况">
            <a-select
              v-model:value="profileForm.employmentStatus"
              allow-clear
              placeholder="请选择"
              @clear="profileForm.employmentStatus = ''"
            >
              <a-select-option value="employed">在职</a-select-option>
              <a-select-option value="self_employed">自由职业 / 个体经营</a-select-option>
              <a-select-option value="student">学生</a-select-option>
              <a-select-option value="retired">退休</a-select-option>
              <a-select-option value="other">其他</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="居住省份">
            <a-input v-model:value="profileForm.residenceProvince" :maxlength="32" placeholder="例如：广东省" />
          </a-form-item>
          <a-form-item label="居住城市">
            <a-input v-model:value="profileForm.residenceCity" :maxlength="32" placeholder="例如：深圳市" />
          </a-form-item>
          <a-form-item label="职业">
            <a-input v-model:value="profileForm.occupation" :maxlength="64" placeholder="例如：产品经理" />
          </a-form-item>
          <a-form-item label="申报年收入（元）">
            <a-input v-model:value="profileForm.annualIncome" type="number" min="0" placeholder="用户主动填写的参考值" />
          </a-form-item>
          <a-form-item label="年度开销预算（元）">
            <a-input v-model:value="profileForm.annualExpenseBudget" type="number" min="0" placeholder="与实际流水统计区分" />
          </a-form-item>
        </div>
        <p class="form-note"><InfoCircleOutlined /> 年龄由出生日期计算，不单独存储。</p>
      </a-form>
    </a-modal>

    <a-drawer
      v-model:open="memoryListOpen"
      placement="right"
      width="min(440px, 100vw)"
      title="全部记忆"
      class="memory-list-drawer"
    >
      <template #extra>
        <a-button type="primary" size="small" :disabled="!memoryEnabled" @click="openNewMemory">
          <PlusOutlined />新增
        </a-button>
      </template>
      <a-alert
        v-if="!memoryEnabled"
        type="info"
        show-icon
        message="记忆功能已关闭"
        description="已有内容仍可查看和管理，但未来不会参与回答。"
      />
      <div v-if="memories.length" class="memory-list">
        <article v-for="memory in memories" :key="memory.id" class="memory-item">
          <div class="memory-item-heading">
            <span>{{ categoryLabels[memory.category] }}</span>
            <small><ClockCircleOutlined /> {{ memory.updatedAt }}</small>
          </div>
          <strong>{{ memory.title }}</strong>
          <p>{{ memory.content }}</p>
          <div class="memory-actions">
            <a-button type="text" size="small" @click="openMemoryEditor(memory)">
              <EditOutlined />编辑
            </a-button>
            <a-button type="text" size="small" danger @click="deleteMemory(memory)">
              <DeleteOutlined />删除
            </a-button>
          </div>
        </article>
      </div>
      <a-empty v-else description="暂无记忆">
        <a-button type="primary" :disabled="!memoryEnabled" @click="openNewMemory">
          新增第一条记忆
        </a-button>
      </a-empty>
    </a-drawer>

    <a-modal
      v-model:open="memoryEditorOpen"
      centered
      :title="editingMemoryId ? '编辑记忆' : '新增记忆'"
      :width="480"
      ok-text="保存预览"
      cancel-text="取消"
      @ok="saveMemoryPreview"
    >
      <a-form layout="vertical">
        <a-form-item label="记忆类型" required>
          <a-select v-model:value="memoryForm.category">
            <a-select-option value="goal">财务目标</a-select-option>
            <a-select-option value="preference">回答偏好</a-select-option>
            <a-select-option value="constraint">财务约束</a-select-option>
            <a-select-option value="personal">个人信息</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="标题" required>
          <a-input v-model:value="memoryForm.title" :maxlength="80" placeholder="一句话概括这条记忆" />
        </a-form-item>
        <a-form-item label="内容" required>
          <a-textarea
            v-model:value="memoryForm.content"
            :maxlength="500"
            :auto-size="{ minRows: 4, maxRows: 8 }"
            placeholder="填写希望 Agent 在后续回答中考虑的信息"
          />
        </a-form-item>
        <a-alert type="info" show-icon message="请勿填写密码、验证码、银行卡号或密钥。" />
      </a-form>
    </a-modal>
  </section>
</template>

<style scoped>
.financial-profile {
  display: flex;
  min-height: 0;
  height: 100%;
  flex-direction: column;
  color: #26262a;
  background: #f7f7f8;
}

.profile-header {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-height: 70px;
  padding: 12px 15px;
  border-bottom: 1px solid #e8e8eb;
  background: #fff;
}

.profile-header > div {
  display: grid;
  gap: 2px;
}

.profile-header span,
.card-kicker {
  color: #9a9aa1;
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.profile-header h2 {
  margin: 0;
  font-size: 16px;
  line-height: 1.25;
}

.preview-badge {
  padding: 4px 7px;
  border-radius: 999px;
  color: #7168f5 !important;
  background: #f0efff;
  letter-spacing: 0 !important;
  white-space: nowrap;
}

.icon-button {
  display: grid;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 1px solid #e7e7ea;
  border-radius: 9px;
  color: #626269;
  background: #fff;
  cursor: pointer;
  place-items: center;
}

.icon-button:hover {
  border-color: #d7d3ff;
  color: #7168f5;
  background: #faf9ff;
}

.icon-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.icon-button.subtle {
  width: 32px;
  height: 32px;
  border: 0;
  background: #f5f5f6;
}

.profile-scroll {
  display: grid;
  gap: 13px;
  min-height: 0;
  padding: 14px;
  overflow-y: auto;
}

.preview-alert :deep(.ant-alert-message),
.preview-alert :deep(.ant-alert-description) {
  font-size: 11px;
}

.memory-card,
.profile-card,
.live-data-note {
  border: 1px solid #e8e8eb;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 5px 18px rgb(30 30 35 / 3%);
}

.memory-card {
  overflow: hidden;
  transition: opacity 160ms ease;
}

.memory-card.is-disabled .memory-preview {
  opacity: 0.64;
}

.card-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 58px;
  padding: 12px 14px;
  border-bottom: 1px solid #ededee;
}

.card-heading > div {
  display: grid;
  gap: 3px;
}

.card-heading strong {
  font-size: 13px;
}

.memory-preview {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 12px 14px 14px;
  border: 0;
  color: inherit;
  background: #fff;
  text-align: left;
  cursor: pointer;
}

.memory-preview:hover {
  background: #fafaff;
}

.memory-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #c7c7cc;
}

.memory-status-dot.active {
  background: #7168f5;
  box-shadow: 0 0 0 4px #efedff;
}

.memory-copy {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.memory-copy small {
  color: #8178ff;
  font-size: 9px;
}

.memory-copy strong {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-copy > span {
  display: -webkit-box;
  overflow: hidden;
  color: #77777f;
  font-size: 10px;
  line-height: 1.55;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.memory-preview > .anticon {
  color: #aaaab0;
  font-size: 11px;
}

.completion-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 10px;
  padding: 11px 14px 5px;
  color: #8c8c93;
  font-size: 9px;
}

.profile-state {
  display: flex;
  min-height: 150px;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 20px;
  color: #77777f;
  font-size: 11px;
}

.profile-state.error {
  flex-direction: column;
}

.completion-row strong {
  color: #7168f5;
}

.completion-row :deep(.ant-progress) {
  grid-column: 1 / -1;
  line-height: 1;
}

.completion-row :deep(.ant-progress-bg) {
  background: #8178ff;
}

.profile-fields {
  margin: 0;
  padding: 4px 14px 10px;
}

.profile-fields > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 43px;
  border-bottom: 1px solid #f0f0f1;
}

.profile-fields > div:last-child {
  border-bottom: 0;
}

.profile-fields dt {
  color: #77777e;
  font-size: 10px;
}

.profile-fields dd {
  margin: 0;
  color: #303034;
  font-size: 11px;
  font-weight: 600;
  text-align: right;
}

.live-data-note {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 10px;
  padding: 13px;
  color: #7168f5;
}

.live-data-note > .anticon {
  display: grid;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: #f0efff;
  place-items: center;
}

.live-data-note > div {
  display: grid;
  gap: 3px;
}

.live-data-note strong {
  color: #3c3c41;
  font-size: 11px;
}

.live-data-note span {
  color: #85858d;
  font-size: 9px;
  line-height: 1.55;
}

.memory-settings {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 18px;
}

.memory-settings > div:first-child {
  display: grid;
  gap: 5px;
}

.memory-settings strong {
  font-size: 14px;
}

.memory-settings span {
  color: #77777f;
  font-size: 12px;
  line-height: 1.6;
}

.memory-settings > .ant-alert {
  grid-column: 1 / -1;
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 14px;
}

.form-grid > :last-child {
  grid-column: 1 / -1;
}

.form-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: #8b8b92;
  font-size: 11px;
}

.memory-list {
  display: grid;
  gap: 12px;
}

.memory-item {
  padding: 15px;
  border: 1px solid #e8e8eb;
  border-radius: 13px;
  background: #fff;
}

.memory-item-heading,
.memory-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.memory-item-heading span {
  padding: 3px 7px;
  border-radius: 999px;
  color: #7168f5;
  background: #f0efff;
  font-size: 10px;
}

.memory-item-heading small {
  color: #a0a0a6;
  font-size: 10px;
}

.memory-item > strong {
  display: block;
  margin-top: 12px;
  font-size: 13px;
}

.memory-item p {
  margin: 7px 0 10px;
  color: #707077;
  font-size: 11px;
  line-height: 1.7;
}

.memory-actions {
  justify-content: flex-end;
  border-top: 1px solid #f0f0f1;
  padding-top: 7px;
}

@media (max-width: 520px) {
  .profile-scroll {
    padding: 12px;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-grid > :last-child {
    grid-column: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .memory-card {
    transition: none;
  }
}
</style>
