<script setup lang="ts">
import {
  ArrowRightOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
  TagOutlined,
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
  isFuture: boolean;
}

const settings = useSettingsStore();
const loading = ref(true);
const currency = ref(settings.preferences.base_currency);
const range = ref<[string, string]>(currentMonthRange());
const summary = ref<FinanceSummary | null>(null);
const accounts = ref<Account[]>([]);
const monthTransactions = ref<Transaction[]>([]);
const dayDetailsOpen = ref(false);
const selectedDate = ref<string | null>(null);

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
const monthNetAmount = computed(() => toNumber(summary.value?.net_cash_flow));
const selectedTransactions = computed(() => {
  if (!selectedDate.value) return [];
  return monthTransactions.value.filter(
    (transaction) =>
      formatDate(transaction.transaction_date) === selectedDate.value,
  );
});
const selectedDayAmount = computed(() =>
  selectedTransactions.value.reduce(
    (total, transaction) => total + transactionSignedAmount(transaction),
    0,
  ),
);
const selectedDateLabel = computed(() =>
  selectedDate.value ? dayjs(selectedDate.value).format("M月D日") : "",
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
      isFuture: dayjs(date).isAfter(dayjs(), "day"),
    };
  });
});

function formatCalendarAmount(day: CalendarDay): string {
  if (day.isFuture) return "—";
  if (!day.hasTransactions) return "0";
  const sign = day.amount > 0 ? "+" : "";
  const amount = new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 2,
  }).format(day.amount);
  return `${sign}${amount}`;
}

function transactionSignedAmount(transaction: Transaction): number {
  const amount = toNumber(transaction.amount);
  return transaction.transaction_type === "income" ? amount : -amount;
}

function formatSignedMoney(
  amount: number,
  amountCurrency = currency.value,
): string {
  if (amount === 0) return formatMoney(0, amountCurrency);
  return `${amount > 0 ? "+" : "-"}${formatMoney(Math.abs(amount), amountCurrency)}`;
}

function openDayDetails(day: CalendarDay): void {
  if (day.isFuture) return;
  selectedDate.value = day.date;
  dayDetailsOpen.value = true;
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
              <div class="month-net">
                <strong
                  class="sensitive-amount"
                  :class="{
                    'money-positive': monthNetAmount > 0,
                    'money-negative': monthNetAmount < 0,
                  }"
                >
                  {{ formatSignedMoney(monthNetAmount) }}
                </strong>
              </div>

              <div class="calendar-grid">
                <button
                  v-for="day in calendarDays"
                  :key="day.date"
                  type="button"
                  class="calendar-day"
                  :class="{
                    'is-selected': selectedDate === day.date,
                    'is-future': day.isFuture,
                  }"
                  :disabled="day.isFuture"
                  :aria-label="`${day.date}，${formatCalendarAmount(day)}`"
                  @click="openDayDetails(day)"
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
                </button>
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
                      <div class="transaction-icon">
                        <TagOutlined />
                      </div>
                      <div class="transaction-copy">
                        <strong>{{ item.category }}</strong>
                        <span>
                          {{ item.description || "无备注" }} ·
                          {{ formatDate(item.transaction_date) }}
                        </span>
                      </div>
                      <SyncOutlined class="transaction-source-icon" />
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

    <a-modal
      v-model:open="dayDetailsOpen"
      centered
      :width="900"
      :footer="null"
      root-class-name="day-details-root"
      wrap-class-name="day-details-modal"
    >
      <template #title>
        <span class="day-details-title">DETAILS</span>
      </template>

      <section class="day-details-content" aria-live="polite">
        <div class="day-details-summary">
          <span>{{ selectedDateLabel }}</span>
          <strong
            class="sensitive-amount"
            :class="{
              'money-positive': selectedDayAmount > 0,
              'money-negative': selectedDayAmount < 0,
            }"
          >
            {{ formatSignedMoney(selectedDayAmount) }}
          </strong>
        </div>

        <div v-if="selectedTransactions.length" class="day-transaction-list">
          <div
            v-for="transaction in selectedTransactions"
            :key="transaction.id"
            class="day-transaction-row"
          >
            <TagOutlined class="day-transaction-tag" />
            <div class="day-transaction-copy">
              <strong>{{ transaction.category }}</strong>
              <span>
                {{ transaction.description || "无备注" }} ·
                {{ selectedDateLabel }}
              </span>
            </div>
            <SyncOutlined class="day-transaction-source" />
            <b
              class="sensitive-amount"
              :class="
                transaction.transaction_type === 'income'
                  ? 'money-positive'
                  : 'money-negative'
              "
            >
              {{
                formatSignedMoney(
                  transactionSignedAmount(transaction),
                  transaction.currency,
                )
              }}
            </b>
          </div>
        </div>
        <a-empty v-else :image="undefined" description="当日暂无交易" />
      </section>
    </a-modal>
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
  width: 100%;
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
  grid-template-columns: minmax(520px, 1.05fr) minmax(420px, 0.95fr);
  align-items: start;
  gap: 24px;
}

.calendar-section,
.recent-section {
  min-width: 0;
}

.month-net {
  display: flex;
  align-items: center;
  min-height: 34px;
  margin-bottom: 12px;
}

.month-net strong {
  color: var(--ink-950);
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -0.025em;
}

.month-net strong.money-positive,
.calendar-day > strong.money-positive,
.day-details-summary > strong.money-positive {
  color: #087f5b;
}

.month-net strong.money-negative,
.calendar-day > strong.money-negative,
.day-details-summary > strong.money-negative {
  color: var(--danger);
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
  min-height: 58px;
  padding: 7px;
  border: 1px solid #e8e8ea;
  border-radius: 8px;
  background: #fafafa;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    background-color 0.16s ease;
}

.calendar-day:not(:disabled):hover,
.calendar-day.is-selected {
  border-color: #b5165d;
  background: #ffffff;
  box-shadow: inset 0 0 0 1px #b5165d;
}

.calendar-day.is-future {
  background: #f8f8f7;
  cursor: default;
}

.calendar-day.is-future > span,
.calendar-day.is-future > strong {
  color: #b0b0b5;
}

.calendar-day > span {
  color: #34343a;
  font-size: 12px;
  font-weight: 500;
}

.calendar-day > strong {
  overflow: hidden;
  color: #242428;
  font-size: 12px;
  font-weight: 550;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 34px;
  margin-bottom: 12px;
}

.recent-heading a {
  color: var(--ink-500);
  font-size: 10px;
  text-decoration: none;
}

.transaction-list :deep(.ant-list-item) {
  padding: 12px 0;
}

.transaction-row {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 10px;
}

.transaction-icon {
  display: grid;
  width: 18px;
  height: 24px;
  flex: 0 0 18px;
  color: #c59111;
  font-size: 16px;
  place-items: center;
}

.transaction-copy {
  display: grid;
  min-width: 0;
  flex: 1;
}

.transaction-copy strong {
  overflow: hidden;
  color: var(--ink-900);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.transaction-copy span {
  overflow: hidden;
  color: var(--ink-500);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.transaction-row > b {
  flex: 0 0 auto;
  min-width: 86px;
  font-size: 12px;
  text-align: right;
}

.transaction-source-icon {
  flex: 0 0 auto;
  color: var(--ink-800);
  font-size: 14px;
}

.day-details-title {
  color: #67676f;
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.22em;
}

.day-details-content {
  padding: 26px 16px 8px;
}

.day-details-summary {
  display: grid;
  justify-items: center;
  margin-bottom: 38px;
}

.day-details-summary > span {
  color: #a0a0a7;
  font-size: 14px;
}

.day-details-summary > strong {
  color: var(--ink-950);
  font-size: 31px;
  font-weight: 500;
  letter-spacing: -0.025em;
}

.day-transaction-list {
  display: grid;
}

.day-transaction-row {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) 22px auto;
  align-items: center;
  gap: 12px;
  min-height: 58px;
  padding: 8px 0;
  border-bottom: 1px solid #eeeeef;
}

.day-transaction-row:last-child {
  border-bottom: 0;
}

.day-transaction-tag {
  color: #c59111;
  font-size: 18px;
}

.day-transaction-copy {
  display: grid;
  min-width: 0;
}

.day-transaction-copy strong {
  overflow: hidden;
  color: var(--ink-950);
  font-size: 15px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.day-transaction-copy span {
  overflow: hidden;
  color: var(--ink-500);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.day-transaction-source {
  color: var(--ink-900);
  font-size: 17px;
}

.day-transaction-row > b {
  min-width: 100px;
  font-size: 15px;
  font-weight: 500;
  text-align: right;
}

:global(.day-details-modal .ant-modal) {
  max-width: calc(100vw - 32px);
}

:global(.day-details-modal .ant-modal-content) {
  overflow: hidden;
  padding: 0;
  border-radius: 30px;
  box-shadow: 0 24px 70px rgb(18 18 20 / 22%);
}

:global(.day-details-modal .ant-modal-header) {
  min-height: 74px;
  margin: 0;
  padding: 27px 24px 20px;
  border-bottom: 1px solid #ececee;
}

:global(.day-details-modal .ant-modal-body) {
  min-height: 250px;
  padding: 0 24px 30px;
}

:global(.day-details-modal .ant-modal-close) {
  top: 19px;
  right: 20px;
  width: 38px;
  height: 38px;
  color: #6d6d75;
  font-size: 18px;
}

:global(.day-details-root .ant-modal-mask) {
  background: rgb(23 23 25 / 48%);
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

  .month-net strong {
    font-size: 22px;
  }

  .calendar-day {
    min-height: 48px;
    padding: 5px 4px;
  }

  .calendar-day > strong {
    font-size: 10px;
  }

  .day-details-content {
    padding-inline: 0;
  }

  .day-transaction-row {
    grid-template-columns: 20px minmax(0, 1fr) auto;
  }

  .day-transaction-source {
    display: none;
  }
}
</style>
