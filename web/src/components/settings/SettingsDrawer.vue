<script setup lang="ts">
import {
  BankOutlined,
  CloseOutlined,
  DeleteOutlined,
  DollarOutlined,
  FontSizeOutlined,
  InfoCircleOutlined,
  LockOutlined,
  LogoutOutlined,
  QuestionCircleOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";

import { apiErrorMessage } from "@/services/http";
import { financeApi } from "@/services/finance";
import { useSettingsStore } from "@/stores/settings";
import type { Account, User } from "@/types/api";
import { accountTypeLabels, formatMoney } from "@/utils/format";

type SettingsPanel =
  | "profile"
  | "security"
  | "accounts"
  | "deactivation"
  | "finance"
  | "appearance"
  | "help"
  | "about";

const props = defineProps<{
  id?: string;
  open: boolean;
  user: User | null;
  loggingOut?: boolean;
  deactivatingAccount?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  changePassword: [];
  manageAccounts: [];
  requestAccountDeactivation: [];
  logout: [];
}>();

const settings = useSettingsStore();
const activePanel = ref<SettingsPanel | null>(null);
const settingsPanel = ref<HTMLElement | null>(null);
const appVersion = import.meta.env.VITE_APP_VERSION || "0.1.0";
const profileForm = reactive({ displayName: "" });
const accounts = ref<Account[]>([]);
const accountsLoading = ref(false);
const accountsLoadFailed = ref(false);
const preferenceForm = reactive({
  defaultAccountId: null as string | null,
  baseCurrency: "CNY",
  timezone: "Asia/Shanghai",
  fontSize: "medium",
  layoutDensity: "comfortable",
  hideSensitiveAmounts: false,
});

const accountStatus = computed(() => {
  const labels: Record<string, string> = {
    active: "正常",
    disabled: "已停用",
    locked: "已锁定",
  };
  return props.user
    ? (labels[props.user.status] ?? props.user.status)
    : "未获取";
});

function syncForms(): void {
  profileForm.displayName = settings.profile.display_name ?? "";
  preferenceForm.baseCurrency = settings.preferences.base_currency;
  preferenceForm.timezone = settings.preferences.timezone;
  preferenceForm.fontSize = settings.preferences.font_size;
  preferenceForm.layoutDensity = settings.preferences.layout_density;
  preferenceForm.hideSensitiveAmounts =
    settings.preferences.hide_sensitive_amounts;
  preferenceForm.defaultAccountId = settings.preferences.default_account_id;
}

async function loadAccounts(): Promise<void> {
  if (accountsLoading.value) return;
  accountsLoading.value = true;
  accountsLoadFailed.value = false;
  try {
    accounts.value = (await financeApi.listAccounts()).items;
  } catch {
    accountsLoadFailed.value = true;
  } finally {
    accountsLoading.value = false;
  }
}

async function loadSettings(): Promise<void> {
  await settings.initialize();
  syncForms();
}

async function loadDrawerData(): Promise<void> {
  await Promise.all([loadSettings(), loadAccounts()]);
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    void loadDrawerData();
  },
  { immediate: true },
);

async function saveProfile(): Promise<void> {
  if (settings.savingProfile) return;
  try {
    await settings.updateProfile(profileForm.displayName.trim() || null);
    message.success("个人档案已保存");
  } catch (error) {
    message.error(apiErrorMessage(error, "个人档案保存失败"));
  }
}

async function saveFinancePreferences(): Promise<void> {
  if (settings.savingPreferences) return;
  try {
    await settings.updatePreferences({
      base_currency: preferenceForm.baseCurrency,
      timezone: preferenceForm.timezone,
    });
    message.success("财务偏好已保存");
  } catch (error) {
    message.error(apiErrorMessage(error, "财务偏好保存失败"));
  }
}

async function saveDefaultAccount(): Promise<void> {
  if (settings.savingPreferences) return;
  try {
    await settings.updatePreferences({
      default_account_id: preferenceForm.defaultAccountId,
    });
    syncForms();
    message.success(
      preferenceForm.defaultAccountId ? "默认账户已保存" : "默认账户已清除",
    );
  } catch (error) {
    message.error(apiErrorMessage(error, "默认账户保存失败"));
  }
}

async function clearDefaultAccount(): Promise<void> {
  preferenceForm.defaultAccountId = null;
  await saveDefaultAccount();
}

async function saveAppearancePreferences(): Promise<void> {
  if (settings.savingPreferences) return;
  try {
    await settings.updatePreferences({
      font_size: preferenceForm.fontSize as "small" | "medium" | "large",
      layout_density: preferenceForm.layoutDensity as "comfortable" | "compact",
      hide_sensitive_amounts: preferenceForm.hideSensitiveAmounts,
    });
    message.success("显示偏好已保存");
  } catch (error) {
    message.error(apiErrorMessage(error, "显示偏好保存失败"));
  }
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "暂无记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "暂无记录";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function togglePanel(panel: SettingsPanel): void {
  activePanel.value = activePanel.value === panel ? null : panel;
}

function close(): void {
  emit("update:open", false);
}

function handleDocumentPointerDown(event: PointerEvent): void {
  if (!props.open || !(event.target instanceof Element)) return;
  if (
    settingsPanel.value?.contains(event.target) ||
    event.target.closest(
      ".settings-trigger, .ant-select-dropdown, .ant-modal-root",
    )
  ) {
    return;
  }
  close();
}

function handleDocumentKeydown(event: KeyboardEvent): void {
  if (props.open && event.key === "Escape") close();
}

onMounted(() => {
  document.addEventListener("pointerdown", handleDocumentPointerDown);
  document.addEventListener("keydown", handleDocumentKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
  document.removeEventListener("keydown", handleDocumentKeydown);
});
</script>

<template>
  <aside
    v-if="open"
    :id="id"
    ref="settingsPanel"
    class="settings-drawer"
    role="dialog"
    aria-modal="false"
    aria-labelledby="settings-title"
  >
    <header class="settings-titlebar">
      <div>
        <span>ACCOUNT &amp; PREFERENCES</span>
        <h2 id="settings-title">设置中心</h2>
      </div>
      <button type="button" aria-label="关闭设置中心" @click="close">
        <CloseOutlined />
      </button>
    </header>

    <div
      class="settings-content"
      :aria-busy="settings.loading || accountsLoading"
    >
      <div class="settings-feedback" aria-live="polite">
        <a-alert
          v-if="settings.loadFailed"
          type="error"
          show-icon
          message="设置资料加载失败"
          description="暂时使用安全默认值，你可以重新加载。"
        >
          <template #action>
            <a-button
              size="small"
              :loading="settings.loading"
              @click="loadSettings"
            >
              重新加载
            </a-button>
          </template>
        </a-alert>
        <span
          v-else-if="settings.loading"
          class="settings-loading-status"
          role="status"
        >
          正在加载设置资料…
        </span>
      </div>

      <section class="account-summary" aria-label="当前账户">
        <a-avatar :size="46" class="settings-avatar">
          <template #icon><UserOutlined /></template>
        </a-avatar>
        <div>
          <strong>{{
            settings.displayName || user?.username || "Aurum 用户"
          }}</strong>
          <span>{{ user?.email ?? "正在读取账户信息" }}</span>
        </div>
        <span class="account-status">{{ accountStatus }}</span>
      </section>

      <section class="settings-group" aria-labelledby="account-settings-title">
        <h3 id="account-settings-title">账户</h3>

        <article
          class="settings-item"
          :class="{ 'is-open': activePanel === 'profile' }"
        >
          <button
            id="settings-trigger-profile"
            type="button"
            class="settings-item-trigger"
            aria-controls="settings-panel-profile"
            :aria-expanded="activePanel === 'profile'"
            @click="togglePanel('profile')"
          >
            <span class="settings-item-icon"><UserOutlined /></span>
            <span class="settings-item-copy">
              <strong>个人档案</strong>
              <small>查看账户身份和注册信息</small>
            </span>
            <RightOutlined class="settings-item-arrow" />
          </button>
          <div
            v-show="activePanel === 'profile'"
            id="settings-panel-profile"
            class="settings-panel"
            role="region"
            aria-labelledby="settings-trigger-profile"
          >
            <a-form
              layout="vertical"
              class="settings-form"
            >
              <a-form-item label="显示昵称">
                <a-input
                  v-model:value="profileForm.displayName"
                  :maxlength="64"
                  placeholder="未设置时显示用户名"
                />
              </a-form-item>
              <dl class="profile-list">
                <div>
                  <dt>用户名</dt>
                  <dd>{{ user?.username ?? "—" }}</dd>
                </div>
                <div>
                  <dt>邮箱</dt>
                  <dd>{{ user?.email ?? "—" }}</dd>
                </div>
                <div>
                  <dt>账户状态</dt>
                  <dd>{{ accountStatus }}</dd>
                </div>
                <div>
                  <dt>注册日期</dt>
                  <dd>{{ formatDate(user?.created_at) }}</dd>
                </div>
              </dl>
              <a-button
                type="primary"
                html-type="button"
                block
                :loading="settings.savingProfile"
                @click="saveProfile"
              >
                保存个人档案
              </a-button>
            </a-form>
          </div>
        </article>

        <article
          class="settings-item"
          :class="{ 'is-open': activePanel === 'security' }"
        >
          <button
            id="settings-trigger-security"
            type="button"
            class="settings-item-trigger"
            aria-controls="settings-panel-security"
            :aria-expanded="activePanel === 'security'"
            @click="togglePanel('security')"
          >
            <span class="settings-item-icon"><SafetyCertificateOutlined /></span>
            <span class="settings-item-copy">
              <strong>安全中心</strong>
              <small>管理登录密码和账户安全</small>
            </span>
            <RightOutlined class="settings-item-arrow" />
          </button>
          <div
            v-show="activePanel === 'security'"
            id="settings-panel-security"
            class="settings-panel"
            role="region"
            aria-labelledby="settings-trigger-security"
          >
            <div class="security-status">
              <LockOutlined />
              <div>
                <strong>登录密码</strong>
                <span>最近修改：{{ formatDate(user?.password_changed_at) }}</span>
              </div>
            </div>
            <a-button type="primary" block @click="emit('changePassword')">
              修改密码
            </a-button>
            <p class="settings-note">
              修改成功后，当前令牌和所有刷新令牌都会失效，需要重新登录。
            </p>
          </div>
        </article>

        <article
          class="settings-item"
          :class="{ 'is-open': activePanel === 'accounts' }"
        >
          <button
            id="settings-trigger-accounts"
            type="button"
            class="settings-item-trigger"
            aria-controls="settings-panel-accounts"
            :aria-expanded="activePanel === 'accounts'"
            @click="togglePanel('accounts')"
          >
            <span class="settings-item-icon"><BankOutlined /></span>
            <span class="settings-item-copy">
              <strong>财务账户</strong>
              <small>查看账户并设置新交易的默认账户</small>
            </span>
            <RightOutlined class="settings-item-arrow" />
          </button>
          <div
            v-show="activePanel === 'accounts'"
            id="settings-panel-accounts"
            class="settings-panel accounts-panel"
            role="region"
            aria-labelledby="settings-trigger-accounts"
          >
            <a-spin :spinning="accountsLoading">
              <a-alert
                v-if="accountsLoadFailed"
                type="warning"
                show-icon
                message="账户列表加载失败"
                description="请检查网络连接后重试。"
              >
                <template #action>
                  <a-button
                    size="small"
                    :loading="accountsLoading"
                    @click="loadAccounts"
                  >
                    重试
                  </a-button>
                </template>
              </a-alert>
              <a-empty
                v-else-if="!accounts.length && !accountsLoading"
                description="暂无有效账户"
              />
              <a-radio-group
                v-else
                v-model:value="preferenceForm.defaultAccountId"
                class="account-options"
              >
                <label
                  v-for="account in accounts"
                  :key="account.id"
                  class="account-option"
                >
                  <a-radio :value="account.id" />
                  <span class="account-option-copy">
                    <span>
                      <strong>{{ account.name }}</strong>
                      <small>{{ accountTypeLabels[account.account_type] }}</small>
                    </span>
                    <span>
                      <strong class="sensitive-amount">
                        {{ formatMoney(account.balance, account.currency) }}
                      </strong>
                      <small>正常 · {{ account.currency }}</small>
                    </span>
                  </span>
                </label>
              </a-radio-group>
            </a-spin>
            <div class="account-actions">
              <a-button type="link" @click="emit('manageAccounts')">
                管理全部账户
              </a-button>
              <a-button
                v-if="settings.preferences.default_account_id"
                type="link"
                danger
                :disabled="settings.savingPreferences"
                @click="clearDefaultAccount"
              >
                清除默认
              </a-button>
              <a-button
                type="primary"
                :disabled="
                  !preferenceForm.defaultAccountId || accountsLoadFailed
                "
                :loading="settings.savingPreferences"
                @click="saveDefaultAccount"
              >
                保存默认账户
              </a-button>
            </div>
            <p class="settings-note">
              默认账户仅用于新建交易时预选；停用或归档后会自动清除。
            </p>
          </div>
        </article>

        <article
          class="settings-item danger-item"
          :class="{ 'is-open': activePanel === 'deactivation' }"
        >
          <button
            id="settings-trigger-deactivation"
            type="button"
            class="settings-item-trigger"
            aria-controls="settings-panel-deactivation"
            :aria-expanded="activePanel === 'deactivation'"
            @click="togglePanel('deactivation')"
          >
            <span class="settings-item-icon"><DeleteOutlined /></span>
            <span class="settings-item-copy">
              <strong>注销账户</strong>
              <small>停用 Aurum 账户并结束所有登录</small>
            </span>
            <RightOutlined class="settings-item-arrow" />
          </button>
          <div
            v-show="activePanel === 'deactivation'"
            id="settings-panel-deactivation"
            class="settings-panel"
            role="region"
            aria-labelledby="settings-trigger-deactivation"
          >
            <a-alert
              type="warning"
              show-icon
              message="注销后将无法再次登录"
              description="现有登录凭证会立即失效。财务与知识库数据不会在此步骤中被物理删除。"
            />
            <a-button
              danger
              block
              class="deactivation-request"
              :loading="deactivatingAccount"
              @click="emit('requestAccountDeactivation')"
            >
              申请注销账户
            </a-button>
            <p class="settings-note">
              下一步仍需输入当前用户名和密码进行二次确认。
            </p>
          </div>
        </article>
      </section>

      <section
        class="settings-group"
        aria-labelledby="preference-settings-title"
      >
        <h3 id="preference-settings-title">偏好</h3>

        <article
          class="settings-item"
          :class="{ 'is-open': activePanel === 'finance' }"
        >
          <button
            id="settings-trigger-finance"
            type="button"
            class="settings-item-trigger"
            aria-controls="settings-panel-finance"
            :aria-expanded="activePanel === 'finance'"
            @click="togglePanel('finance')"
          >
            <span class="settings-item-icon"><DollarOutlined /></span>
            <span class="settings-item-copy">
              <strong>财务偏好</strong>
              <small>设置默认币种和财务统计时区</small>
            </span>
            <RightOutlined class="settings-item-arrow" />
          </button>
          <div
            v-show="activePanel === 'finance'"
            id="settings-panel-finance"
            class="settings-panel"
            role="region"
            aria-labelledby="settings-trigger-finance"
          >
            <a-form
              layout="vertical"
              class="settings-form"
            >
              <a-form-item label="基准币种">
                <a-select v-model:value="preferenceForm.baseCurrency">
                  <a-select-option value="CNY">CNY · 人民币</a-select-option>
                  <a-select-option value="USD">USD · 美元</a-select-option>
                  <a-select-option value="HKD">HKD · 港币</a-select-option>
                </a-select>
              </a-form-item>
              <a-form-item label="财务时区">
                <a-select v-model:value="preferenceForm.timezone" show-search>
                  <a-select-option value="Asia/Shanghai">
                    Asia/Shanghai
                  </a-select-option>
                  <a-select-option value="Asia/Hong_Kong">
                    Asia/Hong_Kong
                  </a-select-option>
                  <a-select-option value="America/New_York">
                    America/New_York
                  </a-select-option>
                  <a-select-option value="Europe/London">
                    Europe/London
                  </a-select-option>
                </a-select>
              </a-form-item>
              <a-button
                type="primary"
                html-type="button"
                block
                :loading="settings.savingPreferences"
                @click="saveFinancePreferences"
              >
                保存财务偏好
              </a-button>
              <p class="settings-note">
                基准币种和时区会影响报表与 Agent 对财务周期的解释。
              </p>
            </a-form>
          </div>
        </article>

        <article
          class="settings-item"
          :class="{ 'is-open': activePanel === 'appearance' }"
        >
          <button
            id="settings-trigger-appearance"
            type="button"
            class="settings-item-trigger"
            aria-controls="settings-panel-appearance"
            :aria-expanded="activePanel === 'appearance'"
            @click="togglePanel('appearance')"
          >
            <span class="settings-item-icon"><FontSizeOutlined /></span>
            <span class="settings-item-copy">
              <strong>显示偏好</strong>
              <small>调整字号、界面密度和金额可见性</small>
            </span>
            <RightOutlined class="settings-item-arrow" />
          </button>
          <div
            v-show="activePanel === 'appearance'"
            id="settings-panel-appearance"
            class="settings-panel"
            role="region"
            aria-labelledby="settings-trigger-appearance"
          >
            <a-form
              layout="vertical"
              class="settings-form"
            >
              <a-form-item label="字号">
                <a-radio-group
                  v-model:value="preferenceForm.fontSize"
                  button-style="solid"
                >
                  <a-radio-button value="small">小</a-radio-button>
                  <a-radio-button value="medium">标准</a-radio-button>
                  <a-radio-button value="large">大</a-radio-button>
                </a-radio-group>
              </a-form-item>
              <a-form-item label="界面密度">
                <a-radio-group
                  v-model:value="preferenceForm.layoutDensity"
                  button-style="solid"
                >
                  <a-radio-button value="comfortable">舒适</a-radio-button>
                  <a-radio-button value="compact">紧凑</a-radio-button>
                </a-radio-group>
              </a-form-item>
              <div class="switch-setting">
                <div>
                  <strong>隐藏敏感金额</strong><span>用圆点遮盖带有敏感标记的金额</span>
                </div>
                <a-switch
                  v-model:checked="preferenceForm.hideSensitiveAmounts"
                />
              </div>
              <a-button
                type="primary"
                html-type="button"
                block
                :loading="settings.savingPreferences"
                @click="saveAppearancePreferences"
              >
                保存显示偏好
              </a-button>
            </a-form>
          </div>
        </article>
      </section>

      <section class="settings-group" aria-labelledby="resource-settings-title">
        <h3 id="resource-settings-title">资源</h3>

        <article
          class="settings-item"
          :class="{ 'is-open': activePanel === 'help' }"
        >
          <button
            id="settings-trigger-help"
            type="button"
            class="settings-item-trigger"
            aria-controls="settings-panel-help"
            :aria-expanded="activePanel === 'help'"
            @click="togglePanel('help')"
          >
            <span class="settings-item-icon"><QuestionCircleOutlined /></span>
            <span class="settings-item-copy">
              <strong>帮助与使用指引</strong>
              <small>快速了解 Aurum 的主要能力</small>
            </span>
            <RightOutlined class="settings-item-arrow" />
          </button>
          <div
            v-show="activePanel === 'help'"
            id="settings-panel-help"
            class="settings-panel"
            role="region"
            aria-labelledby="settings-trigger-help"
          >
            <ul class="help-list">
              <li>在首页查看净现金流、近期收支和账户概览。</li>
              <li>使用左侧导航管理流水、预算和个人投资。</li>
              <li>点击右上角星光图标，或按 Ctrl + / 打开智能问答。</li>
            </ul>
          </div>
        </article>

        <article
          class="settings-item"
          :class="{ 'is-open': activePanel === 'about' }"
        >
          <button
            id="settings-trigger-about"
            type="button"
            class="settings-item-trigger"
            aria-controls="settings-panel-about"
            :aria-expanded="activePanel === 'about'"
            @click="togglePanel('about')"
          >
            <span class="settings-item-icon"><InfoCircleOutlined /></span>
            <span class="settings-item-copy">
              <strong>关于 Aurum</strong>
              <small>版本信息和产品说明</small>
            </span>
            <RightOutlined class="settings-item-arrow" />
          </button>
          <div
            v-show="activePanel === 'about'"
            id="settings-panel-about"
            class="settings-panel about-panel"
            role="region"
            aria-labelledby="settings-trigger-about"
          >
            <div class="about-mark">A</div>
            <div>
              <strong>Aurum Agent</strong>
              <span>个人财务与投资智能工作台</span>
              <small>应用版本 {{ appVersion }}</small>
            </div>
          </div>
        </article>
      </section>

      <button
        type="button"
        class="logout-entry"
        :disabled="loggingOut"
        @click="emit('logout')"
      >
        <LogoutOutlined />
        <span>退出登录</span>
        <RightOutlined />
      </button>
    </div>
  </aside>
</template>

<style scoped>
.settings-drawer {
  position: fixed;
  top: 58px;
  right: 18px;
  z-index: 40;
  display: flex;
  overflow: hidden;
  width: min(372px, calc(100vw - 24px));
  max-height: calc(100vh - 70px);
  border: 1px solid #e4e4e7;
  border-radius: 16px;
  background: #fafafa;
  box-shadow: 0 18px 50px rgb(24 24 27 / 14%);
  flex-direction: column;
}

.settings-titlebar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 58px;
  padding: 10px 12px 10px 15px;
  border-bottom: 1px solid #ececee;
  background: #ffffff;
  flex: 0 0 auto;
}

.settings-titlebar > div {
  display: grid;
  gap: 4px;
}

.settings-titlebar span {
  color: #92929a;
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.18em;
}

.settings-titlebar h2 {
  margin: 0;
  color: #171719;
  font-size: 17px;
}

.settings-titlebar button {
  display: grid;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  color: #717178;
  background: transparent;
  cursor: pointer;
  place-items: center;
}

.settings-titlebar button:hover {
  color: #202024;
  background: #f3f3f4;
}

.settings-titlebar button:focus-visible,
.settings-item-trigger:focus-visible,
.logout-entry:focus-visible {
  outline: 2px solid #8178ff;
  outline-offset: 2px;
}

.settings-content {
  overflow-y: auto;
  min-height: 0;
  padding: 14px 14px 18px;
  background: #fafafa;
  overscroll-behavior: contain;
}

.settings-feedback:not(:empty) {
  margin-bottom: 12px;
}

.settings-loading-status {
  display: block;
  padding: 10px 12px;
  border: 1px solid #e8e8eb;
  border-radius: 10px;
  color: #707078;
  background: #ffffff;
  font-size: 12px;
}

.account-summary {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding: 11px 12px;
  border: 1px solid #e8e8eb;
  border-radius: 14px;
  background: #ffffff;
}

.settings-avatar {
  color: #2d2d31;
  background: #ececee;
}

.account-summary > div {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.account-summary strong,
.account-summary span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-summary strong {
  color: #202024;
  font-size: 14px;
}

.account-summary > div span {
  color: #86868e;
  font-size: 12px;
}

.account-summary .account-status {
  padding: 4px 8px;
  border-radius: 999px;
  color: #40735a;
  background: #edf8f1;
  font-size: 10px;
}

.settings-group {
  margin-bottom: 16px;
}

.settings-group h3 {
  margin: 0 0 7px 3px;
  color: #888890;
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.18em;
}

.settings-item {
  overflow: hidden;
  border: 1px solid #e5e5e8;
  border-bottom-width: 0;
  background: #ffffff;
}

.settings-item:first-of-type {
  border-radius: 12px 12px 0 0;
}

.settings-item:last-of-type {
  border-bottom-width: 1px;
  border-radius: 0 0 12px 12px;
}

.settings-item:only-of-type {
  border-radius: 12px;
}

.settings-item-trigger {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  width: 100%;
  min-height: 54px;
  padding: 8px 12px;
  border: 0;
  color: #26262a;
  background: #ffffff;
  text-align: left;
  cursor: pointer;
}

.settings-item-trigger:hover {
  background: #fafafa;
}

.settings-item-icon {
  display: grid;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  color: #626269;
  background: #f3f3f4;
  font-size: 14px;
  place-items: center;
}

.settings-item-copy {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.settings-item-copy strong {
  font-size: 13px;
  font-weight: 600;
}

.settings-item-copy small {
  overflow: hidden;
  color: #8a8a92;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-item-arrow {
  color: #9a9aa1;
  font-size: 11px;
  transition: transform 0.18s ease;
}

.settings-item.is-open .settings-item-arrow {
  transform: rotate(90deg);
}

.settings-panel {
  padding: 2px 12px 14px 51px;
  border-top: 1px solid #eeeeef;
  background: #ffffff;
}

.profile-list {
  margin: 0 0 14px;
}

.settings-form {
  padding-top: 14px;
}

.settings-form :deep(.ant-form-item) {
  margin-bottom: 14px;
}

.settings-form :deep(.ant-select),
.settings-form :deep(.ant-radio-group) {
  width: 100%;
}

.settings-form :deep(.ant-radio-button-wrapper) {
  width: 33.333%;
  text-align: center;
}

.switch-setting {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 4px 0 16px;
}

.switch-setting > div {
  display: grid;
  gap: 4px;
}

.switch-setting strong {
  color: #303035;
  font-size: 12px;
}

.switch-setting span {
  color: #8a8a92;
  font-size: 11px;
}

.profile-list div {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 8px 0;
}

.profile-list dt {
  color: #898991;
  font-size: 12px;
}

.profile-list dd {
  overflow: hidden;
  max-width: 68%;
  margin: 0;
  color: #303035;
  font-size: 12px;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-note {
  margin: 12px 0 0;
  color: #9999a0;
  font-size: 11px;
  line-height: 1.65;
}

.security-status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 14px 0;
  color: #5f5f67;
}

.security-status > div {
  display: grid;
  gap: 3px;
}

.security-status strong {
  color: #303035;
  font-size: 12px;
}

.security-status span {
  color: #8a8a92;
  font-size: 11px;
}

.accounts-panel {
  padding-top: 14px;
}

.account-options {
  display: grid;
  width: 100%;
  gap: 8px;
}

.account-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border: 1px solid #e8e8eb;
  border-radius: 10px;
  cursor: pointer;
}

.account-option:has(.ant-radio-checked) {
  border-color: #aaa4ff;
  background: #faf9ff;
}

.account-option-copy {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
  width: 100%;
  gap: 12px;
}

.account-option-copy > span {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.account-option-copy > span:last-child {
  text-align: right;
}

.account-option-copy strong {
  overflow: hidden;
  color: #303035;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-option-copy small {
  color: #8a8a92;
  font-size: 10px;
}

.account-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 14px;
}

.help-list {
  margin: 14px 0 0;
  padding-left: 18px;
  color: #5f5f67;
  font-size: 12px;
  line-height: 1.7;
}

.help-list li + li {
  margin-top: 7px;
}

.about-panel {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 16px;
}

.about-mark {
  display: grid;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  color: #ffffff;
  background: #26262a;
  font-family: Georgia, serif;
  font-size: 22px;
  place-items: center;
}

.about-panel > div:last-child {
  display: grid;
  gap: 3px;
}

.about-panel strong {
  color: #27272b;
  font-size: 13px;
}

.about-panel span,
.about-panel small {
  color: #8a8a92;
  font-size: 11px;
}

.logout-entry {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 11px;
  width: 100%;
  min-height: 48px;
  padding: 0 13px;
  border: 1px solid #ffd9d7;
  border-radius: 12px;
  color: #d94545;
  background: #ffffff;
  text-align: left;
  cursor: pointer;
}

.logout-entry:hover:not(:disabled) {
  background: #fff8f7;
}

.logout-entry:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.danger-item .settings-item-icon,
.danger-item .settings-item-copy strong {
  color: #d94545;
}

.deactivation-request {
  margin-top: 14px;
}

@media (max-width: 520px) {
  .settings-drawer {
    top: 58px;
    right: 8px;
    width: calc(100vw - 16px);
    max-height: calc(100vh - 66px);
    border-radius: 14px;
  }

  .settings-content {
    padding: 12px 10px 16px;
  }

  .settings-titlebar h2 {
    font-size: 18px;
  }

  .account-summary {
    margin-bottom: 14px;
    padding: 11px;
  }

  .settings-item-trigger {
    grid-template-columns: 30px minmax(0, 1fr) auto;
    min-height: 54px;
    padding: 8px 10px;
  }

  .settings-panel {
    padding: 4px 12px 16px;
  }

  .account-summary .account-status {
    display: none;
  }

  .account-option-copy {
    align-items: flex-start;
    flex-direction: column;
    gap: 7px;
  }

  .account-option-copy > span:last-child {
    text-align: left;
  }

  .account-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .account-actions :deep(.ant-btn) {
    width: 100%;
  }

  .profile-list div {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .profile-list dd {
    max-width: 100%;
    text-align: left;
  }
}

@media (prefers-reduced-motion: reduce) {
  .settings-item-arrow {
    transition: none;
  }
}
</style>
