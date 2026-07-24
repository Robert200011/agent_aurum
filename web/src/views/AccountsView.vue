<script setup lang="ts">
import {
  BankOutlined,
  EditOutlined,
  PlusOutlined,
  StopOutlined,
  WalletOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { financeApi } from '@/services/finance'
import { apiErrorMessage } from '@/services/http'
import type { Account, AccountInput, AccountType } from '@/types/api'
import { accountTypeLabels, formatDate, formatMoney, toNumber } from '@/utils/format'

const loading = ref(false)
const saving = ref(false)
const modalOpen = ref(false)
const includeInactive = ref(false)
const accounts = ref<Account[]>([])
const editing = ref<Account | null>(null)
const form = reactive<AccountInput & { is_active: boolean }>({
  name: '',
  account_type: 'checking',
  currency: 'CNY',
  opening_balance: 0,
  is_active: true,
})

const activeAccounts = computed(() => accounts.value.filter((item) => item.is_active))
const totalByCurrency = computed(() => {
  const totals = new Map<string, number>()
  for (const account of activeAccounts.value) {
    totals.set(account.currency, (totals.get(account.currency) ?? 0) + toNumber(account.balance))
  }
  return [...totals.entries()]
})

const columns = [
  { title: '账户', key: 'account', dataIndex: 'name' },
  { title: '类型', key: 'account_type', dataIndex: 'account_type', width: 130 },
  { title: '币种', dataIndex: 'currency', width: 90 },
  { title: '当前余额', key: 'balance', dataIndex: 'balance', align: 'right' as const },
  { title: '状态', key: 'status', width: 100 },
  { title: '更新时间', key: 'updated_at', dataIndex: 'updated_at', width: 130 },
  { title: '操作', key: 'actions', width: 130, fixed: 'right' as const },
]

async function loadAccounts(): Promise<void> {
  loading.value = true
  try {
    accounts.value = (await financeApi.listAccounts(includeInactive.value)).items
  } catch (error) {
    message.error(apiErrorMessage(error, '账户列表加载失败'))
  } finally {
    loading.value = false
  }
}

function resetForm(): void {
  Object.assign(form, {
    name: '',
    account_type: 'checking' as AccountType,
    currency: 'CNY',
    opening_balance: 0,
    is_active: true,
  })
}

function openCreate(): void {
  editing.value = null
  resetForm()
  modalOpen.value = true
}

function openEdit(account: Account): void {
  editing.value = account
  Object.assign(form, {
    name: account.name,
    account_type: account.account_type,
    currency: account.currency,
    opening_balance: 0,
    is_active: account.is_active,
  })
  modalOpen.value = true
}

async function saveAccount(): Promise<void> {
  saving.value = true
  try {
    if (editing.value) {
      await financeApi.updateAccount(editing.value.id, {
        name: form.name.trim(),
        account_type: form.account_type,
        is_active: form.is_active,
      })
      message.success('账户信息已更新')
    } else {
      await financeApi.createAccount({
        name: form.name.trim(),
        account_type: form.account_type,
        currency: form.currency,
        opening_balance: form.opening_balance,
      })
      message.success('账户创建成功')
    }
    modalOpen.value = false
    await loadAccounts()
  } catch (error) {
    message.error(apiErrorMessage(error, '账户保存失败'))
  } finally {
    saving.value = false
  }
}

function archiveAccount(account: Account): void {
  Modal.confirm({
    title: `归档“${account.name}”？`,
    content: '归档后不能再记入新交易，但历史数据和报表仍会保留。',
    okText: '确认归档',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await financeApi.archiveAccount(account.id)
        message.success('账户已归档')
        await loadAccounts()
      } catch (error) {
        message.error(apiErrorMessage(error, '账户归档失败'))
      }
    },
  })
}

onMounted(loadAccounts)
</script>

<template>
  <div class="page-shell">
    <div class="page-heading">
      <div>
        <h1>账户管理</h1>
        <p>维护现金、储蓄、信用与投资账户。余额由期初值和交易自动推导，不能直接改写。</p>
      </div>
      <a-button type="primary" size="large" @click="openCreate"><PlusOutlined />新建账户</a-button>
    </div>

    <section class="account-summary">
      <article class="account-summary-card">
        <div class="summary-icon"><BankOutlined /></div>
        <div><span>有效账户</span><strong>{{ activeAccounts.length }}</strong></div>
      </article>
      <article v-for="[currency, total] in totalByCurrency" :key="currency" class="account-summary-card">
        <div class="summary-icon gold"><WalletOutlined /></div>
        <div><span>{{ currency }} 总余额</span><strong>{{ formatMoney(total, currency) }}</strong></div>
      </article>
    </section>

    <a-card class="surface-card table-card" :bordered="false">
      <div class="table-toolbar">
        <div>
          <strong>资金账户</strong>
          <span>共 {{ accounts.length }} 个账户</span>
        </div>
        <a-switch
          v-model:checked="includeInactive"
          checked-children="含已归档"
          un-checked-children="仅有效"
          @change="loadAccounts"
        />
      </div>
      <a-table
        :columns="columns"
        :data-source="accounts"
        :loading="loading"
        :pagination="false"
        :scroll="{ x: 820 }"
        row-key="id"
      >
        <template #bodyCell="{ column, record }: { column: { key: string }; record: Account }">
          <template v-if="column.key === 'account'">
            <div class="account-name">
              <div><BankOutlined /></div>
              <span><strong>{{ record.name }}</strong><small>创建于 {{ formatDate(record.created_at) }}</small></span>
            </div>
          </template>
          <template v-else-if="column.key === 'account_type'">
            {{ accountTypeLabels[record.account_type] }}
          </template>
          <template v-else-if="column.key === 'balance'">
            <strong :class="toNumber(record.balance) < 0 ? 'money-negative' : ''">
              {{ formatMoney(record.balance, record.currency) }}
            </strong>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.is_active ? 'green' : 'default'">
              {{ record.is_active ? '正常' : '已归档' }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'updated_at'">
            <span class="muted">{{ formatDate(record.updated_at) }}</span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button type="link" class="table-action" @click="openEdit(record)">
                <EditOutlined />编辑
              </a-button>
              <a-button
                v-if="record.is_active"
                type="link"
                danger
                class="table-action"
                @click="archiveAccount(record)"
              >
                <StopOutlined />归档
              </a-button>
            </a-space>
          </template>
        </template>
        <template #emptyText>
          <a-empty description="还没有资金账户">
            <a-button type="primary" @click="openCreate">创建第一个账户</a-button>
          </a-empty>
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="modalOpen"
      :title="editing ? '编辑账户' : '新建账户'"
      :confirm-loading="saving"
      ok-text="保存账户"
      cancel-text="取消"
      @ok="saveAccount"
    >
      <a-form layout="vertical" :model="form" class="account-form">
        <a-form-item label="账户名称" required>
          <a-input v-model:value="form.name" placeholder="例如：日常消费卡" />
        </a-form-item>
        <a-form-item label="账户类型" required>
          <a-select v-model:value="form.account_type">
            <a-select-option
              v-for="(label, value) in accountTypeLabels"
              :key="value"
              :value="value"
            >
              {{ label }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <div class="form-grid">
          <a-form-item label="币种" required>
            <a-select v-model:value="form.currency" :disabled="Boolean(editing)">
              <a-select-option value="CNY">CNY</a-select-option>
              <a-select-option value="USD">USD</a-select-option>
              <a-select-option value="HKD">HKD</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item v-if="!editing" label="期初余额" required>
            <a-input-number v-model:value="form.opening_balance" :precision="2" style="width: 100%" />
          </a-form-item>
          <a-form-item v-else label="账户状态">
            <a-switch
              v-model:checked="form.is_active"
              checked-children="正常"
              un-checked-children="归档"
            />
          </a-form-item>
        </div>
        <a-alert
          v-if="!editing"
          type="info"
          show-icon
          message="期初余额不会生成虚构交易，后续余额由收支交易自动维护。"
        />
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.account-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.account-summary-card {
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
.account-name > div {
  display: grid;
  width: 42px;
  height: 42px;
  border-radius: 13px;
  color: var(--mint-700);
  background: var(--mint-100);
  font-size: 18px;
  place-items: center;
}

.summary-icon.gold {
  color: #987122;
  background: #fbf2dd;
}

.account-summary-card > div:last-child {
  display: grid;
}

.account-summary-card span,
.table-toolbar span {
  color: var(--ink-500);
  font-size: 11px;
}

.account-summary-card strong {
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
  padding: 0 0 20px;
}

.table-toolbar > div {
  display: grid;
}

.table-toolbar strong {
  color: var(--ink-950);
  font-size: 16px;
}

.account-name {
  display: flex;
  align-items: center;
  gap: 10px;
}

.account-name > div {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  font-size: 14px;
}

.account-name > span {
  display: grid;
}

.account-name strong {
  color: var(--ink-900);
  font-size: 12px;
}

.account-name small {
  color: var(--ink-500);
  font-size: 9px;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

@media (max-width: 560px) {
  .form-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
