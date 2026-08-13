<script setup lang="ts">
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons-vue";
import { message, Modal } from "ant-design-vue";
import dayjs, { type Dayjs } from "dayjs";
import { computed, onMounted, reactive, ref } from "vue";

import { financeApi } from "@/services/finance";
import { apiErrorMessage } from "@/services/http";
import { useSettingsStore } from "@/stores/settings";
import type {
  Budget,
  BudgetInput,
  BudgetPeriod,
  FinanceSummary,
} from "@/types/api";
import {
  budgetPeriodLabels,
  currentMonthRange,
  formatDate,
  formatMoney,
  toNumber,
} from "@/utils/format";

const settings = useSettingsStore();
const loading = ref(false);
const saving = ref(false);
const modalOpen = ref(false);
const budgets = ref<Budget[]>([]);
const summary = ref<FinanceSummary | null>(null);
const editing = ref<Budget | null>(null);
const currency = ref(settings.preferences.base_currency);
const monthRange = currentMonthRange();
const form = reactive({
  category: "",
  period: "monthly" as BudgetPeriod,
  amount: 0,
  currency: settings.preferences.base_currency,
  range: [dayjs().startOf("month"), dayjs().endOf("month")] as [Dayjs, Dayjs],
});

const executionMap = computed(
  () =>
    new Map(summary.value?.budgets.map((item) => [item.budget_id, item]) ?? []),
);
const aggregatePercent = computed(() => {
  const amount = toNumber(summary.value?.budget_amount);
  return amount
    ? Math.round((toNumber(summary.value?.budget_spent) / amount) * 100)
    : 0;
});

async function loadBudgets(): Promise<void> {
  loading.value = true;
  try {
    const [list, report] = await Promise.all([
      financeApi.listBudgets({ currency: currency.value }),
      financeApi.financeSummary(monthRange[0], monthRange[1], currency.value),
    ]);
    budgets.value = list.items;
    summary.value = report;
  } catch (error) {
    message.error(apiErrorMessage(error, "预算数据加载失败"));
  } finally {
    loading.value = false;
  }
}

function resetForm(): void {
  Object.assign(form, {
    category: "",
    period: "monthly" as BudgetPeriod,
    amount: 0,
    currency: currency.value,
    range: [dayjs().startOf("month"), dayjs().endOf("month")] as [Dayjs, Dayjs],
  });
}

function openCreate(): void {
  editing.value = null;
  resetForm();
  modalOpen.value = true;
}

function openEdit(budget: Budget): void {
  editing.value = budget;
  Object.assign(form, {
    category: budget.category,
    period: budget.period,
    amount: Number(budget.amount),
    currency: budget.currency,
    range: [dayjs(budget.start_date), dayjs(budget.end_date)] as [Dayjs, Dayjs],
  });
  modalOpen.value = true;
}

async function saveBudget(): Promise<void> {
  if (!form.category.trim()) {
    message.warning("请输入预算分类");
    return;
  }
  const payload: BudgetInput = {
    category: form.category.trim(),
    period: form.period,
    amount: form.amount,
    currency: form.currency,
    start_date: form.range[0].format("YYYY-MM-DD"),
    end_date: form.range[1].format("YYYY-MM-DD"),
  };
  saving.value = true;
  try {
    if (editing.value) {
      await financeApi.updateBudget(editing.value.id, payload);
      message.success("预算已更新");
    } else {
      await financeApi.createBudget(payload);
      message.success("预算已创建");
    }
    modalOpen.value = false;
    await loadBudgets();
  } catch (error) {
    message.error(apiErrorMessage(error, "预算保存失败"));
  } finally {
    saving.value = false;
  }
}

function deleteBudget(budget: Budget): void {
  Modal.confirm({
    title: `删除“${budget.category}”预算？`,
    content: "删除预算不会删除该分类下的任何交易。",
    okText: "确认删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      try {
        await financeApi.deleteBudget(budget.id);
        message.success("预算已删除");
        await loadBudgets();
      } catch (error) {
        message.error(apiErrorMessage(error, "预算删除失败"));
      }
    },
  });
}

function executionPercent(budget: Budget): number {
  return Math.round(
    toNumber(executionMap.value.get(budget.id)?.utilization_percent),
  );
}

onMounted(loadBudgets);
</script>

<template>
  <div class="page-shell">
    <div class="page-heading">
      <div>
        <h1>预算管理</h1>
        <p>
          按分类与日期范围规划支出。预算执行基于实际交易分类，超支不会被静默截断。
        </p>
      </div>
      <a-button type="primary" size="large" @click="openCreate">
        <PlusOutlined />创建预算
      </a-button>
    </div>

    <section class="budget-hero">
      <div class="budget-ring">
        <a-progress
          type="circle"
          :percent="Math.min(100, aggregatePercent)"
          :size="112"
          :stroke-color="aggregatePercent > 100 ? '#d84f4f' : '#5b75f7'"
        >
          <template #format>
            <span class="ring-value">{{ aggregatePercent }}%</span>
          </template>
        </a-progress>
      </div>
      <div class="budget-hero-copy">
        <span>本月预算执行</span>
        <h2 class="sensitive-amount">
          {{ formatMoney(summary?.budget_spent, currency) }} /
          {{ formatMoney(summary?.budget_amount, currency) }}
        </h2>
        <p>{{ monthRange[0] }} 至 {{ monthRange[1] }} · {{ currency }}</p>
      </div>
      <div class="remaining-panel">
        <span>本月剩余额度</span>
        <strong
          class="sensitive-amount"
          :class="
            toNumber(summary?.budget_remaining) < 0 ? 'money-negative' : ''
          "
        >
          {{ formatMoney(summary?.budget_remaining, currency) }}
        </strong>
        <small><ThunderboltOutlined />实时关联已分类支出</small>
      </div>
      <a-select
        v-model:value="currency"
        class="currency-select"
        @change="loadBudgets"
      >
        <a-select-option value="CNY">CNY</a-select-option>
        <a-select-option value="USD">USD</a-select-option>
        <a-select-option value="HKD">HKD</a-select-option>
      </a-select>
    </section>

    <a-spin :spinning="loading">
      <section v-if="budgets.length" class="budget-grid">
        <article
          v-for="budget in budgets"
          :key="budget.id"
          class="budget-item surface-card"
        >
          <header>
            <div>
              <span>{{ budgetPeriodLabels[budget.period] }}预算</span>
              <h3>{{ budget.category }}</h3>
            </div>
            <a-dropdown>
              <a-button type="text">•••</a-button>
              <template #overlay>
                <a-menu>
                  <a-menu-item @click="openEdit(budget)">
                    <EditOutlined />编辑
                  </a-menu-item>
                  <a-menu-item danger @click="deleteBudget(budget)">
                    <DeleteOutlined />删除
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </header>
          <div class="budget-amount">
            <strong class="sensitive-amount">{{
              formatMoney(
                executionMap.get(budget.id)?.spent_amount ?? 0,
                budget.currency,
              )
            }}</strong>
            <span class="sensitive-amount">预算 {{ formatMoney(budget.amount, budget.currency) }}</span>
          </div>
          <a-progress
            :percent="Math.min(100, executionPercent(budget))"
            :show-info="false"
            :stroke-color="
              executionPercent(budget) > 100 ? '#d84f4f' : '#5b75f7'
            "
          />
          <footer>
            <span>{{ formatDate(budget.start_date, "MM.DD") }}—{{
              formatDate(budget.end_date, "MM.DD")
            }}</span>
            <b :class="executionPercent(budget) > 100 ? 'money-negative' : ''">
              {{ executionPercent(budget) }}%
            </b>
          </footer>
        </article>
      </section>
      <a-card v-else class="surface-card" :bordered="false">
        <a-empty description="当前币种还没有预算">
          <a-button type="primary" @click="openCreate">创建第一笔预算</a-button>
        </a-empty>
      </a-card>
    </a-spin>

    <a-modal
      v-model:open="modalOpen"
      :title="editing ? '编辑预算' : '创建预算'"
      :confirm-loading="saving"
      ok-text="保存预算"
      cancel-text="取消"
      @ok="saveBudget"
    >
      <a-form layout="vertical" :model="form">
        <a-form-item label="预算分类" required>
          <a-input
            v-model:value="form.category"
            placeholder="需要与交易分类保持一致"
          />
        </a-form-item>
        <div class="form-grid">
          <a-form-item label="周期标签" required>
            <a-select v-model:value="form.period">
              <a-select-option
                v-for="(label, value) in budgetPeriodLabels"
                :key="value"
                :value="value"
              >
                {{ label }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="币种" required>
            <a-select v-model:value="form.currency">
              <a-select-option value="CNY">CNY</a-select-option>
              <a-select-option value="USD">USD</a-select-option>
              <a-select-option value="HKD">HKD</a-select-option>
            </a-select>
          </a-form-item>
        </div>
        <a-form-item label="预算金额" required>
          <a-input-number
            v-model:value="form.amount"
            :min="0"
            :precision="2"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="生效日期范围" required>
          <a-range-picker v-model:value="form.range" style="width: 100%" />
        </a-form-item>
        <a-alert
          type="info"
          show-icon
          message="同一分类、币种的预算日期不能重叠，日期两端均包含在统计范围内。"
        />
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.budget-hero {
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 24px;
  padding: 28px 32px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #ffffff;
}

.ring-value {
  color: var(--ink-950);
  font-family: "Iowan Old Style", serif;
  font-size: 22px;
  font-weight: 650;
}

.budget-hero-copy {
  display: grid;
  gap: 4px;
}

.budget-hero-copy > span,
.remaining-panel span {
  color: var(--ink-500);
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.08em;
}

.budget-hero-copy h2 {
  margin: 0;
  color: var(--ink-950);
  font-family: inherit;
  font-size: clamp(24px, 3vw, 34px);
}

.budget-hero-copy p {
  margin: 0;
  color: var(--ink-500);
  font-size: 10px;
}

.remaining-panel {
  display: grid;
  min-width: 210px;
  padding: 18px 22px;
  border-left: 1px solid var(--line);
}

.remaining-panel strong {
  margin: 4px 0;
  color: var(--ink-950);
  font-size: 21px;
}

.remaining-panel small {
  color: var(--mint-700);
  font-size: 9px;
}

.currency-select {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 84px;
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.budget-item {
  padding: 22px;
}

.budget-item header,
.budget-item footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.budget-item header > div {
  display: grid;
}

.budget-item header span {
  color: var(--mint-700);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.budget-item h3 {
  margin: 3px 0 0;
  color: var(--ink-950);
  font-size: 17px;
}

.budget-amount {
  display: grid;
  margin: 26px 0 14px;
}

.budget-amount strong {
  color: var(--ink-950);
  font-family: inherit;
  font-size: 26px;
}

.budget-amount span,
.budget-item footer {
  color: var(--ink-500);
  font-size: 10px;
}

.budget-item footer {
  margin-top: 12px;
}

.budget-item footer b {
  color: var(--mint-700);
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

@media (max-width: 1050px) {
  .budget-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .budget-hero {
    grid-template-columns: 1fr;
  }

  .budget-ring {
    display: none;
  }

  .remaining-panel {
    padding: 18px 0 0;
    border-top: 1px solid var(--line);
    border-left: 0;
  }

  .budget-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
