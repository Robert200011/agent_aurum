<script setup lang="ts">
import {
  ArrowDownOutlined,
  ArrowRightOutlined,
  ArrowUpOutlined,
  BankOutlined,
  FundOutlined,
  ReloadOutlined,
  WalletOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { financeApi } from '@/services/finance'
import { apiErrorMessage } from '@/services/http'
import { useAuthStore } from '@/stores/auth'
import type {
  Account,
  FinanceSummary,
  PortfolioSummary,
  Transaction,
} from '@/types/api'
import { activeAccountsForCurrency } from '@/utils/finance'
import { currentMonthRange, formatDate, formatMoney, toNumber } from '@/utils/format'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(true)
const currency = ref('CNY')
const range = ref<[string, string]>(currentMonthRange())
const summary = ref<FinanceSummary | null>(null)
const portfolio = ref<PortfolioSummary | null>(null)
const accounts = ref<Account[]>([])
const recentTransactions = ref<Transaction[]>([])
const selectedAccounts = computed(() => activeAccountsForCurrency(accounts.value, currency.value))

const greeting = computed(() => {
  const hour = dayjs().hour()
  if (hour < 11) return '早上好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

const budgetUtilization = computed(() => {
  if (!summary.value || toNumber(summary.value.budget_amount) === 0) return 0
  return Math.round(
    (toNumber(summary.value.budget_spent) / toNumber(summary.value.budget_amount)) * 100,
  )
})

async function loadDashboard(): Promise<void> {
  loading.value = true
  const [startDate, endDate] = range.value
  try {
    const [financeSummary, portfolioSummary, accountList, transactionList] = await Promise.all([
      financeApi.financeSummary(startDate, endDate, currency.value),
      financeApi.portfolioSummary(currency.value),
      financeApi.listAccounts(),
      financeApi.listTransactions({
        currency: currency.value,
        page: 1,
        page_size: 6,
      }),
    ])
    summary.value = financeSummary
    portfolio.value = portfolioSummary
    accounts.value = accountList.items
    recentTransactions.value = transactionList.items
  } catch (error) {
    message.error(apiErrorMessage(error, '财务总览加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)
</script>

<template>
  <div class="page-shell">
    <section class="dashboard-hero">
      <div>
        <span class="hero-kicker">{{ greeting }}，{{ auth.user?.username }}</span>
        <h1>你的财务全景，<br />从清晰开始。</h1>
        <p>
          当前展示 {{ range[0] }} 至 {{ range[1] }} 的 {{ currency }} 现金流；
          账户余额与投资组合使用最新账本状态。
        </p>
      </div>
      <div class="hero-actions">
        <a-select v-model:value="currency" style="width: 100px" @change="loadDashboard">
          <a-select-option value="CNY">CNY</a-select-option>
          <a-select-option value="USD">USD</a-select-option>
          <a-select-option value="HKD">HKD</a-select-option>
        </a-select>
        <a-button :loading="loading" @click="loadDashboard"><ReloadOutlined />刷新数据</a-button>
      </div>
      <div class="hero-orbit" aria-hidden="true">
        <span />
        <span />
      </div>
    </section>

    <a-skeleton :loading="loading" active :paragraph="{ rows: 8 }">
      <section class="metric-grid">
        <article class="metric-card balance-card">
          <div class="metric-icon"><WalletOutlined /></div>
          <span>{{ currency }} 当前账户余额</span>
          <strong>{{ formatMoney(summary?.account_balance, currency) }}</strong>
          <small>{{ selectedAccounts.length }} 个 {{ currency }} 有效账户</small>
        </article>
        <article class="metric-card">
          <div class="metric-icon income"><ArrowDownOutlined /></div>
          <span>本月收入</span>
          <strong>{{ formatMoney(summary?.income, currency) }}</strong>
          <small class="money-positive">流入 · 包含边界日期</small>
        </article>
        <article class="metric-card">
          <div class="metric-icon expense"><ArrowUpOutlined /></div>
          <span>本月支出</span>
          <strong>{{ formatMoney(summary?.expense, currency) }}</strong>
          <small class="money-negative">流出 · 按分类聚合</small>
        </article>
        <article class="metric-card">
          <div class="metric-icon portfolio"><FundOutlined /></div>
          <span>投资组合市值</span>
          <strong>{{ formatMoney(portfolio?.total_market_value, currency) }}</strong>
          <small>
            未实现收益
            <b
              :class="
                toNumber(portfolio?.total_unrealized_gain) >= 0
                  ? 'money-positive'
                  : 'money-negative'
              "
            >
              {{ formatMoney(portfolio?.total_unrealized_gain, currency) }}
            </b>
          </small>
        </article>
      </section>

      <section class="dashboard-grid">
        <a-card class="surface-card cash-card" :bordered="false">
          <template #title>
            <div class="card-title">
              <div><span>MONTHLY FLOW</span><strong>现金流概览</strong></div>
              <router-link to="/transactions">查看明细 <ArrowRightOutlined /></router-link>
            </div>
          </template>
          <div class="cash-flow-number">
            <span>净现金流</span>
            <strong
              :class="
                toNumber(summary?.net_cash_flow) >= 0 ? 'money-positive' : 'money-negative'
              "
            >
              {{ formatMoney(summary?.net_cash_flow, currency) }}
            </strong>
          </div>
          <div class="flow-visual">
            <div>
              <span>收入</span>
              <i
                class="income-bar"
                :style="{
                  width: `${Math.min(100, (toNumber(summary?.income) / Math.max(toNumber(summary?.income), toNumber(summary?.expense), 1)) * 100)}%`,
                }"
              />
            </div>
            <div>
              <span>支出</span>
              <i
                class="expense-bar"
                :style="{
                  width: `${Math.min(100, (toNumber(summary?.expense) / Math.max(toNumber(summary?.income), toNumber(summary?.expense), 1)) * 100)}%`,
                }"
              />
            </div>
          </div>
          <div class="flow-legend">
            <span><i class="income-dot" />收入 {{ formatMoney(summary?.income, currency) }}</span>
            <span><i class="expense-dot" />支出 {{ formatMoney(summary?.expense, currency) }}</span>
          </div>
        </a-card>

        <a-card class="surface-card budget-card" :bordered="false">
          <template #title>
            <div class="card-title">
              <div><span>BUDGET PULSE</span><strong>预算执行</strong></div>
              <router-link to="/budgets">管理预算 <ArrowRightOutlined /></router-link>
            </div>
          </template>
          <div v-if="summary?.budgets.length" class="budget-overview">
            <a-progress
              type="dashboard"
              :percent="Math.min(100, budgetUtilization)"
              :stroke-color="budgetUtilization > 100 ? '#d84f4f' : '#0f766e'"
              :width="126"
            >
              <template #format>
                <div class="progress-copy">
                  <strong>{{ budgetUtilization }}%</strong>
                  <span>已使用</span>
                </div>
              </template>
            </a-progress>
            <div class="budget-values">
              <span>预算总额<strong>{{ formatMoney(summary.budget_amount, currency) }}</strong></span>
              <span>已使用<strong>{{ formatMoney(summary.budget_spent, currency) }}</strong></span>
              <span>剩余额度<strong>{{ formatMoney(summary.budget_remaining, currency) }}</strong></span>
            </div>
          </div>
          <a-empty v-else :image="undefined" description="本月还没有预算">
            <a-button type="primary" @click="router.push('/budgets')">创建第一笔预算</a-button>
          </a-empty>
        </a-card>
      </section>

      <section class="dashboard-grid lower-grid">
        <a-card class="surface-card" :bordered="false">
          <template #title>
            <div class="card-title">
              <div><span>RECENT LEDGER</span><strong>最近交易</strong></div>
              <router-link to="/transactions">全部交易 <ArrowRightOutlined /></router-link>
            </div>
          </template>
          <a-list :data-source="recentTransactions" class="transaction-list">
            <template #renderItem="{ item }">
              <a-list-item>
                <div class="transaction-row">
                  <div
                    class="transaction-icon"
                    :class="item.transaction_type === 'income' ? 'is-income' : 'is-expense'"
                  >
                    <ArrowDownOutlined v-if="item.transaction_type === 'income'" />
                    <ArrowUpOutlined v-else />
                  </div>
                  <div class="transaction-copy">
                    <strong>{{ item.category }}</strong>
                    <span>{{ item.description || '无备注' }} · {{ formatDate(item.transaction_date) }}</span>
                  </div>
                  <b
                    :class="item.transaction_type === 'income' ? 'money-positive' : 'money-negative'"
                  >
                    {{ item.transaction_type === 'income' ? '+' : '-'
                    }}{{ formatMoney(item.amount, item.currency) }}
                  </b>
                </div>
              </a-list-item>
            </template>
            <template #empty>
              <a-empty :image="undefined" description="暂无交易记录" />
            </template>
          </a-list>
        </a-card>

        <a-card class="surface-card accounts-card" :bordered="false">
          <template #title>
            <div class="card-title">
              <div><span>ACCOUNTS</span><strong>{{ currency }} 资金账户</strong></div>
              <router-link to="/accounts">管理账户 <ArrowRightOutlined /></router-link>
            </div>
          </template>
          <div v-if="selectedAccounts.length" class="account-stack">
            <div
              v-for="account in selectedAccounts.slice(0, 4)"
              :key="account.id"
              class="account-row"
            >
              <div class="account-icon"><BankOutlined /></div>
              <div>
                <strong>{{ account.name }}</strong>
                <span>{{ account.currency }} · {{ account.is_active ? '正常' : '已归档' }}</span>
              </div>
              <b>{{ formatMoney(account.balance, account.currency) }}</b>
            </div>
          </div>
          <a-empty v-else :image="undefined" :description="`暂无 ${currency} 账户`" />
        </a-card>
      </section>
    </a-skeleton>
  </div>
</template>

<style scoped>
.dashboard-hero {
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  min-height: 250px;
  padding: clamp(28px, 4vw, 48px);
  border-radius: 24px;
  color: white;
  background:
    radial-gradient(circle at 84% 10%, rgb(45 175 151 / 30%), transparent 18rem),
    linear-gradient(135deg, #0a2c29, #0b211f);
  box-shadow: 0 24px 60px rgb(9 37 34 / 17%);
  overflow: hidden;
}

.dashboard-hero > div:first-child {
  position: relative;
  z-index: 2;
}

.hero-kicker {
  color: #d8b766;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.dashboard-hero h1 {
  margin: 12px 0;
  font-family: 'Iowan Old Style', 'Songti SC', serif;
  font-size: clamp(34px, 4vw, 54px);
  font-weight: 560;
  letter-spacing: -0.04em;
  line-height: 1.12;
}

.dashboard-hero p {
  max-width: 650px;
  margin: 0;
  color: rgb(226 242 237 / 62%);
  line-height: 1.7;
}

.hero-actions {
  position: relative;
  z-index: 2;
  display: flex;
  gap: 10px;
}

.hero-actions :deep(.ant-select-selector),
.hero-actions .ant-btn {
  border-color: rgb(255 255 255 / 12%);
  color: white;
  background: rgb(255 255 255 / 8%);
}

.hero-orbit span {
  position: absolute;
  top: -150px;
  right: -80px;
  width: 360px;
  height: 360px;
  border: 1px solid rgb(213 162 63 / 15%);
  border-radius: 50%;
}

.hero-orbit span:last-child {
  top: -104px;
  right: -34px;
  width: 270px;
  height: 270px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.metric-card {
  display: grid;
  min-width: 0;
  padding: 22px;
  border: 1px solid var(--line);
  border-radius: 17px;
  background: rgb(255 255 255 / 90%);
  box-shadow: 0 12px 32px rgb(11 37 34 / 5%);
}

.metric-icon {
  display: grid;
  width: 38px;
  height: 38px;
  margin-bottom: 20px;
  border-radius: 11px;
  color: #0f766e;
  background: #ddf4ee;
  place-items: center;
}

.metric-icon.income {
  color: #087f5b;
  background: #e5f7ef;
}

.metric-icon.expense {
  color: #c24141;
  background: #fbecec;
}

.metric-icon.portfolio {
  color: #987122;
  background: #fbf2dd;
}

.metric-card > span {
  color: var(--ink-500);
  font-size: 12px;
}

.metric-card > strong {
  margin: 7px 0;
  overflow: hidden;
  color: var(--ink-950);
  font-family: 'Iowan Old Style', Georgia, serif;
  font-size: clamp(23px, 2.2vw, 31px);
  font-weight: 600;
  letter-spacing: -0.025em;
  text-overflow: ellipsis;
}

.metric-card small {
  color: var(--ink-500);
  font-size: 10px;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 1.18fr 0.82fr;
  gap: 18px;
}

.lower-grid {
  grid-template-columns: 1.25fr 0.75fr;
}

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.card-title > div {
  display: grid;
  gap: 2px;
}

.card-title span {
  color: var(--mint-700);
  font-size: 8px;
  font-weight: 750;
  letter-spacing: 0.14em;
}

.card-title strong {
  color: var(--ink-950);
  font-family: 'Iowan Old Style', 'Songti SC', serif;
  font-size: 19px;
}

.card-title a {
  color: var(--ink-500);
  font-size: 11px;
  font-weight: 500;
}

.cash-flow-number {
  display: grid;
  margin-bottom: 30px;
}

.cash-flow-number span {
  color: var(--ink-500);
  font-size: 11px;
}

.cash-flow-number strong {
  margin-top: 4px;
  font-family: 'Iowan Old Style', Georgia, serif;
  font-size: 34px;
}

.flow-visual {
  display: grid;
  gap: 16px;
}

.flow-visual > div {
  display: grid;
  grid-template-columns: 38px 1fr;
  align-items: center;
  gap: 12px;
}

.flow-visual span {
  color: var(--ink-500);
  font-size: 11px;
}

.flow-visual i {
  display: block;
  min-width: 6px;
  height: 12px;
  border-radius: 0 8px 8px 0;
}

.income-bar {
  background: linear-gradient(90deg, #0f766e, #42b99f);
}

.expense-bar {
  background: linear-gradient(90deg, #d84f4f, #ed8b78);
}

.flow-legend {
  display: flex;
  gap: 20px;
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  color: var(--ink-500);
  font-size: 10px;
}

.flow-legend i {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 6px;
  border-radius: 50%;
}

.income-dot {
  background: #0f766e;
}

.expense-dot {
  background: #d84f4f;
}

.budget-overview {
  display: flex;
  align-items: center;
  gap: 28px;
  min-height: 170px;
}

.progress-copy {
  display: grid;
}

.progress-copy strong {
  color: var(--ink-950);
  font-family: 'Iowan Old Style', serif;
  font-size: 24px;
}

.progress-copy span {
  color: var(--ink-500);
  font-size: 9px;
}

.budget-values {
  display: grid;
  flex: 1;
  gap: 12px;
}

.budget-values span {
  display: flex;
  justify-content: space-between;
  color: var(--ink-500);
  font-size: 11px;
}

.budget-values strong {
  color: var(--ink-900);
}

.transaction-list :deep(.ant-list-item) {
  padding: 12px 0;
}

.transaction-row {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 12px;
}

.transaction-icon {
  display: grid;
  width: 36px;
  height: 36px;
  border-radius: 11px;
  place-items: center;
}

.transaction-icon.is-income {
  color: #087f5b;
  background: #e7f6ef;
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
  color: var(--ink-900);
  font-size: 12px;
}

.transaction-copy span {
  overflow: hidden;
  color: var(--ink-500);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.transaction-row > b {
  font-size: 12px;
}

.account-stack {
  display: grid;
  gap: 14px;
}

.account-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
}

.account-icon {
  display: grid;
  width: 36px;
  height: 36px;
  border-radius: 11px;
  color: var(--mint-700);
  background: #e8f3ef;
  place-items: center;
}

.account-row > div:nth-child(2) {
  display: grid;
}

.account-row strong,
.account-row b {
  color: var(--ink-900);
  font-size: 11px;
}

.account-row span {
  color: var(--ink-500);
  font-size: 9px;
}

@media (max-width: 1180px) {
  .metric-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .dashboard-grid,
  .lower-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 700px) {
  .dashboard-hero {
    align-items: flex-start;
    flex-direction: column;
    gap: 24px;
  }

  .hero-actions {
    width: 100%;
  }

  .hero-actions .ant-btn {
    flex: 1;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }

  .budget-overview {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
