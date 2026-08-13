<script setup lang="ts">
import {
  ArrowDownOutlined,
  ArrowRightOutlined,
  ArrowUpOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import dayjs from "dayjs";
import { computed, onMounted, ref } from "vue";

import OverviewHeader from "@/components/OverviewHeader.vue";
import { financeApi } from "@/services/finance";
import { apiErrorMessage } from "@/services/http";
import { useSettingsStore } from "@/stores/settings";
import type { Account, FinanceSummary, Transaction } from "@/types/api";
import { activeAccountsForCurrency } from "@/utils/finance";
import {
  currentMonthRange,
  formatDate,
  formatMoney,
  toNumber,
} from "@/utils/format";

interface CalendarDay {
  date: string;
  day: number;
  amount: number;
  hasTransactions: boolean;
}

const settings = useSettingsStore();
const loading = ref(true);
const currency = ref(settings.preferences.base_currency);
const range = ref<[string, string]>(currentMonthRange());
const summary = ref<FinanceSummary | null>(null);
const accounts = ref<Account[]>([]);
const monthTransactions = ref<Transaction[]>([]);

const selectedAccounts = computed(() =>
  activeAccountsForCurrency(accounts.value, currency.value),
);
const recentTransactions = computed(() =>
  [...monthTransactions.value]
    .sort((left, right) =>
      right.transaction_date.localeCompare(left.transaction_date),
    )
    .slice(0, 5),
);

const calendarDays = computed<CalendarDay[]>(() => {
  const start = dayjs(range.value[0]);
  const totals = new Map<string, number>();
  const datesWithTransactions = new Set<string>();

  for (const transaction of monthTransactions.value) {
    const date = formatDate(transaction.transaction_date);
    const signedAmount =
      transaction.transaction_type === "income"
        ? toNumber(transaction.amount)
        : -toNumber(transaction.amount);
    totals.set(date, (totals.get(date) ?? 0) + signedAmount);
    datesWithTransactions.add(date);
  }

  return Array.from({ length: start.daysInMonth() }, (_, index) => {
    const date = start.date(index + 1).format("YYYY-MM-DD");
    return {
      date,
      day: index + 1,
      amount: totals.get(date) ?? 0,
      hasTransactions: datesWithTransactions.has(date),
    };
  });
});

function formatCalendarAmount(day: CalendarDay): string {
  if (!day.hasTransactions) return "—";
  const sign = day.amount > 0 ? "+" : "";
  const amount = new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 2,
  }).format(day.amount);
  return `${sign}${amount}`;
}

async function loadDashboard(): Promise<void> {
  loading.value = true;
  const [startDate, endDate] = range.value;
  try {
    const [financeSummary, accountList, transactionList] = await Promise.all([
      financeApi.financeSummary(startDate, endDate, currency.value),
      financeApi.listAccounts(),
      financeApi.listTransactions({
        currency: currency.value,
        start_date: startDate,
        end_date: endDate,
        page: 1,
        page_size: 200,
      }),
    ]);
    summary.value = financeSummary;
    accounts.value = accountList.items;
    monthTransactions.value = transactionList.items;
  } catch (error) {
    message.error(apiErrorMessage(error, "财务总览加载失败"));
  } finally {
    loading.value = false;
  }
}

onMounted(loadDashboard);
</script>

<template>
  <div class="page-shell dashboard-page">
    <OverviewHeader compact>
      <template #actions>
        <div class="hero-actions">
          <a-select
            v-model:value="currency"
            style="width: 100px"
            @change="loadDashboard"
          >
            <a-select-option value="CNY">CNY</a-select-option>
            <a-select-option value="USD">USD</a-select-option>
            <a-select-option value="HKD">HKD</a-select-option>
          </a-select>
          <a-button :loading="loading" @click="loadDashboard">
            <ReloadOutlined />刷新数据
          </a-button>
        </div>
      </template>
    </OverviewHeader>

    <a-skeleton :loading="loading" active :paragraph="{ rows: 8 }">
      <main class="overview-column">
        <a-card class="surface-card net-cash-card" :bordered="false">
          <template #title>
            <div class="section-heading">
              <span>NET CASH</span>
              <strong>净现金流</strong>
            </div>
          </template>
          <div class="net-cash-summary">
            <strong class="sensitive-amount">{{
              formatMoney(summary?.account_balance, currency)
            }}</strong>
            <span>账户总净现金 · {{ selectedAccounts.length }} 个有效账户</span>
          </div>
          <router-link class="account-entry" to="/accounts">
            <PlusOutlined />添加账户
          </router-link>
        </a-card>

        <a-card class="surface-card monthly-card" :bordered="false">
          <template #title>
            <div class="monthly-card-title">
              <router-link to="/transactions">
                本月收入和支出 <ArrowRightOutlined />
              </router-link>
            </div>
          </template>

          <div class="monthly-content">
            <section class="calendar-section" aria-label="本月每日收支">
              <div class="month-totals">
                <div>
                  <span>本月收入</span>
                  <strong class="money-positive sensitive-amount">{{
                    formatMoney(summary?.income, currency)
                  }}</strong>
                </div>
                <div>
                  <span>本月支出</span>
                  <strong class="money-negative sensitive-amount">{{
                    formatMoney(summary?.expense, currency)
                  }}</strong>
                </div>
              </div>

              <div class="calendar-grid">
                <div
                  v-for="day in calendarDays"
                  :key="day.date"
                  class="calendar-day"
                >
                  <span>{{ day.day }}</span>
                  <strong
                    :class="{
                      'sensitive-amount': day.hasTransactions,
                      'money-positive': day.hasTransactions && day.amount > 0,
                      'money-negative': day.hasTransactions && day.amount < 0,
                    }"
                  >
                    {{ formatCalendarAmount(day) }}
                  </strong>
                </div>
              </div>
            </section>

            <section class="recent-section">
              <div class="recent-heading">
                <span>RECENT TRANSACTIONS</span>
                <router-link to="/transactions">
                  全部交易 <ArrowRightOutlined />
                </router-link>
              </div>

              <a-list
                :data-source="recentTransactions"
                class="transaction-list"
              >
                <template #renderItem="{ item }">
                  <a-list-item>
                    <div class="transaction-row">
                      <div
                        class="transaction-icon"
                        :class="
                          item.transaction_type === 'income'
                            ? 'is-income'
                            : 'is-expense'
                        "
                      >
                        <ArrowDownOutlined
                          v-if="item.transaction_type === 'income'"
                        />
                        <ArrowUpOutlined v-else />
                      </div>
                      <div class="transaction-copy">
                        <strong>{{ item.category }}</strong>
                        <span>{{ item.description || "无备注" }} ·
                          {{ formatDate(item.transaction_date) }}</span>
                      </div>
                      <b
                        class="sensitive-amount"
                        :class="
                          item.transaction_type === 'income'
                            ? 'money-positive'
                            : 'money-negative'
                        "
                      >
                        {{ item.transaction_type === "income" ? "+" : "-"
                        }}{{ formatMoney(item.amount, item.currency) }}
                      </b>
                    </div>
                  </a-list-item>
                </template>
                <template #empty>
                  <a-empty :image="undefined" description="本月暂无交易" />
                </template>
              </a-list>
            </section>
          </div>
        </a-card>
      </main>
    </a-skeleton>
  </div>
</template>

<style scoped>
.dashboard-page {
  width: 100%;
  max-width: 1560px;
  margin: 0 auto;
  padding-inline: clamp(20px, 3vw, 56px);
  gap: 14px;
}

.hero-actions {
  position: relative;
  z-index: 2;
  display: flex;
  gap: 10px;
}

.hero-actions :deep(.ant-select-selector),
.hero-actions .ant-btn {
  border-color: #d8d8dc;
  color: var(--ink-900);
  background: #ffffff;
}

.overview-column {
  display: grid;
  width: min(100%, 1060px);
  gap: 14px;
}

.dashboard-page :deep(.surface-card .ant-card-head) {
  min-height: 48px;
  padding: 0 18px;
}

.dashboard-page :deep(.surface-card .ant-card-head-title) {
  padding: 10px 0;
}

.dashboard-page :deep(.surface-card .ant-card-body) {
  padding: 18px;
}

.section-heading {
  display: grid;
  gap: 2px;
}

.section-heading span,
.recent-heading > span {
  color: var(--ink-500);
  font-size: 8px;
  font-weight: 750;
  letter-spacing: 0.14em;
}

.section-heading strong {
  color: var(--ink-950);
  font-size: 16px;
  font-weight: 550;
}

.net-cash-summary {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 0 2px 16px;
}

.net-cash-summary strong {
  color: var(--ink-950);
  font-size: clamp(23px, 2vw, 29px);
  font-weight: 500;
  letter-spacing: -0.025em;
}

.net-cash-summary span {
  color: var(--ink-500);
  font-size: 11px;
}

.account-entry {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  width: 100%;
  height: 38px;
  border: 1px solid #cfcfd4;
  border-radius: 8px;
  color: var(--ink-900);
  font-size: 12px;
  font-weight: 550;
  text-decoration: none;
  transition: background-color 0.18s ease;
}

.account-entry:hover {
  color: var(--ink-950);
  background: #f7f7f8;
}

.monthly-card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.monthly-card-title > a {
  color: var(--ink-500);
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.13em;
  text-decoration: none;
}

.monthly-content {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(340px, 0.95fr);
  gap: 22px;
}

.calendar-section,
.recent-section {
  min-width: 0;
}

.month-totals {
  display: flex;
  gap: 28px;
  margin-bottom: 14px;
}

.month-totals > div {
  display: grid;
  gap: 2px;
}

.month-totals span {
  color: var(--ink-500);
  font-size: 10px;
}

.month-totals strong {
  font-size: 21px;
  font-weight: 500;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 3px;
}

.calendar-day {
  display: grid;
  align-content: space-between;
  min-width: 0;
  min-height: 52px;
  padding: 6px;
  border: 1px solid #e8e8ea;
  border-radius: 8px;
  background: #fafafa;
}

.calendar-day > span {
  color: #99999f;
  font-size: 10px;
}

.calendar-day > strong {
  overflow: hidden;
  color: #b0b0b5;
  font-size: 9px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 31px;
  margin-bottom: 4px;
}

.recent-heading a {
  color: var(--ink-500);
  font-size: 10px;
  text-decoration: none;
}

.transaction-list :deep(.ant-list-item) {
  padding: 10px 0;
}

.transaction-row {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 10px;
}

.transaction-icon {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  border-radius: 8px;
  place-items: center;
}

.transaction-icon.is-income {
  color: #4f6ff5;
  background: #eef1ff;
}

.transaction-icon.is-expense {
  color: #c24141;
  background: #fbecec;
}

.transaction-copy {
  display: grid;
  min-width: 0;
  flex: 1;
}

.transaction-copy strong {
  overflow: hidden;
  color: var(--ink-900);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.transaction-copy span {
  overflow: hidden;
  color: var(--ink-500);
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.transaction-row > b {
  flex: 0 0 auto;
  font-size: 11px;
}

@media (max-width: 1100px) {
  .monthly-content {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .dashboard-page {
    padding-inline: 0;
  }

  .overview-column {
    width: 100%;
  }
}

@media (max-width: 700px) {
  .hero-actions {
    width: 100%;
  }

  .hero-actions .ant-btn {
    flex: 1;
  }

  .net-cash-summary {
    align-items: flex-start;
    flex-direction: column;
    gap: 3px;
  }

  .month-totals {
    gap: 18px;
  }

  .month-totals strong {
    font-size: 18px;
  }

  .calendar-day {
    min-height: 48px;
    padding: 5px 4px;
  }

  .calendar-day > strong {
    font-size: 8px;
  }
}
</style>
