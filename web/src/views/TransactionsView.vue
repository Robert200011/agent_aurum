<script setup lang="ts">
import {
  DeleteOutlined,
  EditOutlined,
  FileExcelOutlined,
  FilterOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons-vue";
import { message, Modal } from "ant-design-vue";
import dayjs, { type Dayjs } from "dayjs";
import { computed, onMounted, reactive, ref } from "vue";

import { financeApi } from "@/services/finance";
import { apiErrorMessage } from "@/services/http";
import { useSettingsStore } from "@/stores/settings";
import type {
  Account,
  Transaction,
  TransactionInput,
  TransactionType,
} from "@/types/api";
import { formatDate, formatMoney } from "@/utils/format";
import { defaultAccountForTransaction } from "@/utils/finance";

const settings = useSettingsStore();
const loading = ref(false);
const saving = ref(false);
const importLoading = ref(false);
const modalOpen = ref(false);
const importOpen = ref(false);
const accounts = ref<Account[]>([]);
const transactions = ref<Transaction[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const editing = ref<Transaction | null>(null);
const dateRange = ref<[Dayjs, Dayjs] | undefined>();
const selectedFile = ref<File | null>(null);
const importAccountId = ref<string>();
const strictImport = ref(true);

const filters = reactive({
  account_id: undefined as string | undefined,
  transaction_type: undefined as TransactionType | undefined,
  category: "",
  search: "",
  currency: undefined as string | undefined,
});

const form = reactive({
  account_id: "",
  transaction_type: "expense" as TransactionType,
  amount: 0,
  currency: settings.preferences.base_currency,
  category: "",
  description: "",
  transaction_date: dayjs(),
});

const accountMap = computed(
  () => new Map(accounts.value.map((item) => [item.id, item])),
);
const activeAccounts = computed(() =>
  accounts.value.filter((item) => item.is_active),
);

const columns = [
  { title: "日期", dataIndex: "transaction_date", key: "date", width: 112 },
  { title: "分类与备注", key: "category", minWidth: 210 },
  { title: "账户", key: "account", width: 150 },
  { title: "类型", key: "type", width: 90 },
  { title: "金额", key: "amount", align: "right" as const, width: 145 },
  { title: "来源", dataIndex: "source", key: "source", width: 90 },
  { title: "操作", key: "actions", width: 125, fixed: "right" as const },
];

async function loadAccounts(): Promise<void> {
  accounts.value = (await financeApi.listAccounts(true)).items;
}

async function loadTransactions(): Promise<void> {
  loading.value = true;
  try {
    const result = await financeApi.listTransactions({
      account_id: filters.account_id,
      transaction_type: filters.transaction_type,
      category: filters.category.trim() || undefined,
      search: filters.search.trim() || undefined,
      currency: filters.currency,
      start_date: dateRange.value?.[0].format("YYYY-MM-DD"),
      end_date: dateRange.value?.[1].format("YYYY-MM-DD"),
      page: page.value,
      page_size: pageSize.value,
    });
    transactions.value = result.items;
    total.value = result.total;
  } catch (error) {
    message.error(apiErrorMessage(error, "交易列表加载失败"));
  } finally {
    loading.value = false;
  }
}

function search(): void {
  page.value = 1;
  void loadTransactions();
}

function resetFilters(): void {
  Object.assign(filters, {
    account_id: undefined,
    transaction_type: undefined,
    category: "",
    search: "",
    currency: undefined,
  });
  dateRange.value = undefined;
  search();
}

function resetForm(): void {
  const firstAccount = defaultAccountForTransaction(
    accounts.value,
    settings.preferences.default_account_id,
  );
  Object.assign(form, {
    account_id: firstAccount?.id ?? "",
    transaction_type: "expense" as TransactionType,
    amount: 0,
    currency: firstAccount?.currency ?? settings.preferences.base_currency,
    category: "",
    description: "",
    transaction_date: dayjs(),
  });
}

function syncFormCurrency(accountId: string): void {
  const account = accountMap.value.get(accountId);
  if (account) form.currency = account.currency;
}

function openCreate(): void {
  editing.value = null;
  resetForm();
  modalOpen.value = true;
}

function openEdit(transaction: Transaction): void {
  editing.value = transaction;
  Object.assign(form, {
    account_id: transaction.account_id,
    transaction_type: transaction.transaction_type,
    amount: Number(transaction.amount),
    currency: transaction.currency,
    category: transaction.category,
    description: transaction.description ?? "",
    transaction_date: dayjs(transaction.transaction_date),
  });
  modalOpen.value = true;
}

async function saveTransaction(): Promise<void> {
  if (!form.account_id || !form.category.trim()) {
    message.warning("请选择账户并填写交易分类");
    return;
  }
  const payload: TransactionInput = {
    account_id: form.account_id,
    transaction_type: form.transaction_type,
    amount: form.amount,
    currency: form.currency,
    category: form.category.trim(),
    description: form.description.trim() || null,
    transaction_date: form.transaction_date.format("YYYY-MM-DD"),
    source: "manual",
  };

  saving.value = true;
  try {
    if (editing.value) {
      await financeApi.updateTransaction(editing.value.id, {
        account_id: payload.account_id,
        transaction_type: payload.transaction_type,
        amount: payload.amount,
        currency: payload.currency,
        category: payload.category,
        description: payload.description,
        transaction_date: payload.transaction_date,
      });
      message.success("交易已更新，账户余额已同步重算");
    } else {
      await financeApi.createTransaction(payload);
      message.success("交易已记录");
    }
    modalOpen.value = false;
    await loadTransactions();
  } catch (error) {
    message.error(apiErrorMessage(error, "交易保存失败"));
  } finally {
    saving.value = false;
  }
}

function deleteTransaction(transaction: Transaction): void {
  Modal.confirm({
    title: "删除这笔交易？",
    content: "删除后系统会自动冲销它对账户余额的影响。",
    okText: "确认删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      try {
        await financeApi.deleteTransaction(transaction.id);
        message.success("交易已删除，余额已冲销");
        await loadTransactions();
      } catch (error) {
        message.error(apiErrorMessage(error, "交易删除失败"));
      }
    },
  });
}

function selectImportFile(event: Event): void {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
}

async function importFile(): Promise<void> {
  if (!importAccountId.value || !selectedFile.value) {
    message.warning("请选择目标账户和导入文件");
    return;
  }
  importLoading.value = true;
  try {
    const result = await financeApi.importTransactions(
      importAccountId.value,
      selectedFile.value,
      strictImport.value,
    );
    if (result.errors.length) {
      Modal.warning({
        title: result.committed ? "部分数据已导入" : "文件未导入",
        width: 620,
        content: `${result.imported_rows} 行导入，${result.skipped_rows} 行跳过，${result.errors.length} 个错误。首个错误：第 ${result.errors[0]?.row ?? "-"} 行 ${result.errors[0]?.message ?? ""}`,
      });
    } else {
      message.success(
        `导入完成：新增 ${result.imported_rows} 行，跳过 ${result.skipped_rows} 行`,
      );
    }
    importOpen.value = false;
    selectedFile.value = null;
    await loadTransactions();
  } catch (error) {
    message.error(apiErrorMessage(error, "文件导入失败"));
  } finally {
    importLoading.value = false;
  }
}

function changePage(nextPage: number, nextPageSize: number): void {
  page.value = nextPage;
  pageSize.value = nextPageSize;
  void loadTransactions();
}

onMounted(async () => {
  try {
    await Promise.all([settings.initialize(), loadAccounts()]);
    await loadTransactions();
  } catch (error) {
    message.error(apiErrorMessage(error, "交易页面初始化失败"));
  }
});
</script>

<template>
  <div class="page-shell transactions-page">
    <div class="page-heading">
      <div>
        <h1>收支明细</h1>
        <p>
          记录、检索和导入现金流。每次新增、修正或删除都会原子更新对应账户余额。
        </p>
      </div>
      <a-space>
        <a-button @click="importOpen = true">
          <FileExcelOutlined />导入表格
        </a-button>
        <a-button type="primary" @click="openCreate">
          <PlusOutlined />记录交易
        </a-button>
      </a-space>
    </div>

    <a-card class="surface-card filter-card" :bordered="false">
      <div class="filter-grid">
        <a-input
          v-model:value="filters.search"
          allow-clear
          placeholder="搜索分类或备注"
          @press-enter="search"
        >
          <template #prefix><SearchOutlined /></template>
        </a-input>
        <a-select
          v-model:value="filters.account_id"
          allow-clear
          placeholder="全部账户"
        >
          <a-select-option
            v-for="account in accounts"
            :key="account.id"
            :value="account.id"
          >
            {{ account.name }}
          </a-select-option>
        </a-select>
        <a-select
          v-model:value="filters.transaction_type"
          allow-clear
          placeholder="收支类型"
        >
          <a-select-option value="income">收入</a-select-option>
          <a-select-option value="expense">支出</a-select-option>
        </a-select>
        <a-range-picker v-model:value="dateRange" style="width: 100%" />
        <a-button type="primary" @click="search">
          <FilterOutlined />筛选
        </a-button>
        <a-button @click="resetFilters">重置</a-button>
      </div>
    </a-card>

    <a-card class="surface-card table-card" :bordered="false">
      <a-table
        :columns="columns"
        :data-source="transactions"
        :loading="loading"
        :pagination="{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (value: number) => `共 ${value} 笔`,
        }"
        :scroll="{ x: 930 }"
        row-key="id"
        @change="
          (pagination: { current?: number; pageSize?: number }) =>
            changePage(pagination.current ?? 1, pagination.pageSize ?? 20)
        "
      >
        <template
          #bodyCell="{
            column,
            record,
          }: {
            column: { key: string };
            record: Transaction;
          }"
        >
          <template v-if="column.key === 'date'">
            <span class="date-cell">{{
              formatDate(record.transaction_date, "MM-DD")
            }}</span>
            <small>{{ formatDate(record.transaction_date, "YYYY") }}</small>
          </template>
          <template v-else-if="column.key === 'category'">
            <div class="category-cell">
              <strong>{{ record.category }}</strong>
              <span>{{ record.description || "无备注" }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'account'">
            {{ accountMap.get(record.account_id)?.name ?? "未知账户" }}
          </template>
          <template v-else-if="column.key === 'type'">
            <a-tag
              :color="record.transaction_type === 'income' ? 'green' : 'red'"
            >
              {{ record.transaction_type === "income" ? "收入" : "支出" }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'amount'">
            <strong
              class="sensitive-amount"
              :class="
                record.transaction_type === 'income'
                  ? 'money-positive'
                  : 'money-negative'
              "
            >
              {{ record.transaction_type === "income" ? "+" : "-"
              }}{{ formatMoney(record.amount, record.currency) }}
            </strong>
          </template>
          <template v-else-if="column.key === 'source'">
            <span class="muted">{{
              record.source === "import" ? "表格导入" : "手工记录"
            }}</span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button
                type="link"
                class="table-action"
                @click="openEdit(record)"
              >
                <EditOutlined />
              </a-button>
              <a-button
                type="link"
                danger
                class="table-action"
                @click="deleteTransaction(record)"
              >
                <DeleteOutlined />
              </a-button>
            </a-space>
          </template>
        </template>
        <template #emptyText>
          <a-empty description="没有符合条件的交易记录" />
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="modalOpen"
      :title="editing ? '修正交易' : '记录交易'"
      :confirm-loading="saving"
      ok-text="保存交易"
      cancel-text="取消"
      @ok="saveTransaction"
    >
      <a-form layout="vertical" :model="form">
        <div class="form-grid">
          <a-form-item label="收支类型" required>
            <a-segmented
              v-model:value="form.transaction_type"
              :options="[
                { label: '支出', value: 'expense' },
                { label: '收入', value: 'income' },
              ]"
              block
            />
          </a-form-item>
          <a-form-item label="交易日期" required>
            <a-date-picker
              v-model:value="form.transaction_date"
              style="width: 100%"
            />
          </a-form-item>
        </div>
        <a-form-item label="账户" required>
          <a-select
            v-model:value="form.account_id"
            placeholder="选择账户"
            @change="syncFormCurrency"
          >
            <a-select-option
              v-for="account in activeAccounts"
              :key="account.id"
              :value="account.id"
            >
              {{ account.name }} · {{ account.currency }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <div class="form-grid amount-grid">
          <a-form-item label="金额" required>
            <a-input-number
              v-model:value="form.amount"
              :min="0"
              :precision="2"
              style="width: 100%"
            />
          </a-form-item>
          <a-form-item label="币种">
            <a-input v-model:value="form.currency" disabled />
          </a-form-item>
        </div>
        <a-form-item label="分类" required>
          <a-input
            v-model:value="form.category"
            placeholder="例如：餐饮、工资、交通"
          />
        </a-form-item>
        <a-form-item label="备注">
          <a-textarea
            v-model:value="form.description"
            :rows="3"
            placeholder="可选说明"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="importOpen"
      title="导入 CSV / XLSX 交易"
      :confirm-loading="importLoading"
      ok-text="开始导入"
      cancel-text="取消"
      @ok="importFile"
    >
      <div class="import-panel">
        <a-alert
          type="info"
          show-icon
          message="文件需包含 transaction_date、transaction_type、amount、category 列"
          description="可选列：currency、description、external_id。文件上限 10 MiB、10,000 行。"
        />
        <a-form layout="vertical">
          <a-form-item label="目标账户" required>
            <a-select
              v-model:value="importAccountId"
              placeholder="选择导入账户"
            >
              <a-select-option
                v-for="account in activeAccounts"
                :key="account.id"
                :value="account.id"
              >
                {{ account.name }} · {{ account.currency }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="导入文件" required>
            <label class="file-picker">
              <FileExcelOutlined />
              <span>{{ selectedFile?.name ?? "选择 .csv 或 .xlsx 文件" }}</span>
              <input
                type="file"
                accept=".csv,.xlsx"
                @change="selectImportFile"
              />
            </label>
          </a-form-item>
          <a-form-item label="导入策略">
            <a-switch
              v-model:checked="strictImport"
              checked-children="严格模式"
              un-checked-children="部分导入"
            />
            <p class="import-help">
              严格模式遇到任一错误将整批回滚；部分导入会保留有效数据行。
            </p>
          </a-form-item>
        </a-form>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.transactions-page {
  width: 100%;
  max-width: 1560px;
  margin: 0 auto;
  padding-inline: clamp(20px, 3vw, 56px);
  gap: 14px;
}

.transactions-page .page-heading {
  align-items: center;
}

.transactions-page .page-heading h1 {
  font-size: 21px;
  font-weight: 550;
}

.transactions-page .page-heading p {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.5;
}

.filter-card {
  padding: 0;
}

.transactions-page :deep(.filter-card .ant-card-body) {
  padding: 13px 16px;
}

.filter-grid {
  display: grid;
  grid-template-columns: minmax(180px, 1.4fr) minmax(130px, 0.9fr) 110px minmax(
      210px,
      1.2fr
    ) auto auto;
  gap: 8px;
}

.table-card {
  overflow: hidden;
}

.transactions-page :deep(.table-card .ant-card-body) {
  padding: 16px 18px 10px;
}

.transactions-page :deep(.ant-table-thead > tr > th) {
  padding: 9px 10px;
  font-size: 11px;
}

.transactions-page :deep(.ant-table-tbody > tr > td) {
  padding: 8px 10px;
  font-size: 11px;
}

.transactions-page :deep(.ant-table-pagination.ant-pagination) {
  margin: 12px 0 0;
  font-size: 11px;
}

.transactions-page :deep(.ant-tag) {
  margin-inline-end: 0;
  font-size: 10px;
  line-height: 18px;
}

.transactions-page :deep(.table-action) {
  min-width: 26px;
  height: 26px;
}

.date-cell {
  display: block;
  color: var(--ink-900);
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
}

td small {
  color: var(--ink-500);
  font-size: 9px;
}

.category-cell {
  display: grid;
  max-width: 300px;
}

.category-cell strong {
  color: var(--ink-900);
  font-size: 11px;
}

.category-cell span {
  overflow: hidden;
  color: var(--ink-500);
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.amount-grid {
  grid-template-columns: 2fr 1fr;
}

.import-panel {
  display: grid;
  gap: 20px;
}

.file-picker {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 90px;
  padding: 20px;
  border: 1px dashed #a8beb7;
  border-radius: 12px;
  color: var(--mint-700);
  background: #f8f8f9;
  cursor: pointer;
  gap: 10px;
}

.file-picker input {
  display: none;
}

.import-help {
  margin: 8px 0 0;
  color: var(--ink-500);
  font-size: 11px;
}

@media (max-width: 1100px) {
  .filter-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 900px) {
  .transactions-page {
    padding-inline: 0;
  }
}

@media (max-width: 700px) {
  .filter-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }

  .page-heading .ant-space {
    display: grid;
    width: 100%;
    grid-template-columns: 1fr 1fr;
  }

  .transactions-page :deep(.table-card .ant-card-body) {
    padding: 12px;
  }
}
</style>
