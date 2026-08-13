<script setup lang="ts">
import {
  BarChartOutlined,
  DeleteOutlined,
  EditOutlined,
  LineChartOutlined,
  PlusOutlined,
  RiseOutlined,
  SwapOutlined,
} from "@ant-design/icons-vue";
import { message, Modal } from "ant-design-vue";
import dayjs, { type Dayjs } from "dayjs";
import { computed, onMounted, reactive, ref } from "vue";

import { financeApi } from "@/services/finance";
import { apiErrorMessage } from "@/services/http";
import { useSettingsStore } from "@/stores/settings";
import type {
  Account,
  AssetType,
  Holding,
  HoldingInput,
  InvestmentTransaction,
  InvestmentTransactionType,
  MarketSnapshotInput,
  PortfolioSummary,
} from "@/types/api";
import {
  assetTypeLabels,
  formatDate,
  formatMoney,
  formatNumber,
  toNumber,
} from "@/utils/format";

const settings = useSettingsStore();
const loading = ref(false);
const saving = ref(false);
const activeTab = ref("portfolio");
const currency = ref(settings.preferences.base_currency);
const accounts = ref<Account[]>([]);
const holdings = ref<Holding[]>([]);
const trades = ref<InvestmentTransaction[]>([]);
const portfolio = ref<PortfolioSummary | null>(null);
const holdingModalOpen = ref(false);
const tradeModalOpen = ref(false);
const snapshotModalOpen = ref(false);
const editingHolding = ref<Holding | null>(null);
const selectedHolding = ref<Holding | null>(null);

const holdingForm = reactive({
  account_id: "",
  symbol: "",
  asset_type: "stock" as AssetType,
  quantity: 0,
  cost_basis: 0,
  currency: settings.preferences.base_currency,
});
const tradeForm = reactive({
  transaction_type: "buy" as InvestmentTransactionType,
  quantity: 0,
  price: 0,
  fee: 0,
  transaction_at: dayjs() as Dayjs,
});
const snapshotForm = reactive({
  symbol: "",
  asset_type: "stock" as AssetType,
  price: 0,
  currency: settings.preferences.base_currency,
  recorded_at: dayjs() as Dayjs,
  data_source: "manual",
});

const investmentAccounts = computed(() =>
  accounts.value.filter(
    (item) => item.is_active && item.account_type === "investment",
  ),
);
const holdingMap = computed(
  () => new Map(holdings.value.map((item) => [item.id, item])),
);

const holdingColumns = [
  { title: "证券", key: "symbol", minWidth: 160 },
  { title: "账户", key: "account", width: 150 },
  { title: "数量", key: "quantity", align: "right" as const, width: 120 },
  { title: "平均成本", key: "cost_basis", align: "right" as const, width: 140 },
  { title: "成本价值", key: "cost_value", align: "right" as const, width: 150 },
  { title: "操作", key: "actions", width: 160, fixed: "right" as const },
];

const tradeColumns = [
  { title: "成交时间", key: "time", width: 160 },
  { title: "证券", key: "symbol", width: 120 },
  { title: "方向", key: "type", width: 86 },
  { title: "数量", key: "quantity", align: "right" as const },
  { title: "成交价", key: "price", align: "right" as const },
  { title: "手续费", key: "fee", align: "right" as const },
  { title: "已实现收益", key: "gain", align: "right" as const },
];

async function loadData(): Promise<void> {
  loading.value = true;
  try {
    const [accountList, holdingList, tradeList, portfolioSummary] =
      await Promise.all([
        financeApi.listAccounts(),
        financeApi.listHoldings(),
        financeApi.listInvestmentTransactions(),
        financeApi.portfolioSummary(currency.value),
      ]);
    accounts.value = accountList.items;
    holdings.value = holdingList.items;
    trades.value = tradeList.items;
    portfolio.value = portfolioSummary;
  } catch (error) {
    message.error(apiErrorMessage(error, "投资数据加载失败"));
  } finally {
    loading.value = false;
  }
}

function resetHoldingForm(): void {
  const account = investmentAccounts.value.find(
    (item) => item.currency === currency.value,
  );
  Object.assign(holdingForm, {
    account_id: account?.id ?? investmentAccounts.value[0]?.id ?? "",
    symbol: "",
    asset_type: "stock" as AssetType,
    quantity: 0,
    cost_basis: 0,
    currency: account?.currency ?? currency.value,
  });
}

function syncHoldingCurrency(accountId: string): void {
  const account = investmentAccounts.value.find(
    (item) => item.id === accountId,
  );
  if (account) holdingForm.currency = account.currency;
}

function openCreateHolding(): void {
  editingHolding.value = null;
  resetHoldingForm();
  holdingModalOpen.value = true;
}

function openEditHolding(holding: Holding): void {
  editingHolding.value = holding;
  Object.assign(holdingForm, {
    account_id: holding.account_id,
    symbol: holding.symbol,
    asset_type: holding.asset_type,
    quantity: Number(holding.quantity),
    cost_basis: Number(holding.cost_basis),
    currency: holding.currency,
  });
  holdingModalOpen.value = true;
}

async function saveHolding(): Promise<void> {
  if (!holdingForm.account_id || !holdingForm.symbol.trim()) {
    message.warning("请选择投资账户并填写证券代码");
    return;
  }
  saving.value = true;
  try {
    if (editingHolding.value) {
      await financeApi.updateHolding(editingHolding.value.id, {
        asset_type: holdingForm.asset_type,
        quantity: holdingForm.quantity,
        cost_basis: holdingForm.cost_basis,
      });
      message.success("期初持仓已修正");
    } else {
      const payload: HoldingInput = {
        account_id: holdingForm.account_id,
        symbol: holdingForm.symbol.trim().toUpperCase(),
        asset_type: holdingForm.asset_type,
        quantity: holdingForm.quantity,
        cost_basis: holdingForm.cost_basis,
        currency: holdingForm.currency,
      };
      await financeApi.createHolding(payload);
      message.success("期初持仓已创建");
    }
    holdingModalOpen.value = false;
    await loadData();
  } catch (error) {
    message.error(apiErrorMessage(error, "持仓保存失败"));
  } finally {
    saving.value = false;
  }
}

function openTrade(holding: Holding): void {
  selectedHolding.value = holding;
  Object.assign(tradeForm, {
    transaction_type: "buy" as InvestmentTransactionType,
    quantity: 0,
    price: 0,
    fee: 0,
    transaction_at: dayjs(),
  });
  tradeModalOpen.value = true;
}

async function saveTrade(): Promise<void> {
  if (!selectedHolding.value) return;
  saving.value = true;
  try {
    await financeApi.createInvestmentTransaction({
      holding_id: selectedHolding.value.id,
      transaction_type: tradeForm.transaction_type,
      quantity: tradeForm.quantity,
      price: tradeForm.price,
      fee: tradeForm.fee,
      currency: selectedHolding.value.currency,
      transaction_at: tradeForm.transaction_at.toISOString(),
    });
    message.success("投资交易已记入，持仓与现金余额已同步更新");
    tradeModalOpen.value = false;
    await loadData();
  } catch (error) {
    message.error(apiErrorMessage(error, "投资交易保存失败"));
  } finally {
    saving.value = false;
  }
}

function openSnapshot(holding?: Holding): void {
  Object.assign(snapshotForm, {
    symbol: holding?.symbol ?? "",
    asset_type: holding?.asset_type ?? ("stock" as AssetType),
    price: 0,
    currency: holding?.currency ?? currency.value,
    recorded_at: dayjs(),
    data_source: "manual",
  });
  snapshotModalOpen.value = true;
}

async function saveSnapshot(): Promise<void> {
  const payload: MarketSnapshotInput = {
    symbol: snapshotForm.symbol.trim().toUpperCase(),
    asset_type: snapshotForm.asset_type,
    price: snapshotForm.price,
    currency: snapshotForm.currency,
    recorded_at: snapshotForm.recorded_at.toISOString(),
    data_source: snapshotForm.data_source.trim(),
  };
  saving.value = true;
  try {
    await financeApi.createMarketSnapshot(payload);
    message.success("市场价格快照已发布");
    snapshotModalOpen.value = false;
    await loadData();
  } catch (error) {
    message.error(apiErrorMessage(error, "价格快照发布失败"));
  } finally {
    saving.value = false;
  }
}

function deleteHolding(holding: Holding): void {
  Modal.confirm({
    title: `删除 ${holding.symbol} 持仓？`,
    content: "仅数量为零且没有投资交易历史的持仓可以删除。",
    okText: "确认删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      try {
        await financeApi.deleteHolding(holding.id);
        message.success("持仓已删除");
        await loadData();
      } catch (error) {
        message.error(apiErrorMessage(error, "持仓删除失败"));
      }
    },
  });
}

onMounted(loadData);
</script>

<template>
  <div class="page-shell">
    <div class="page-heading">
      <div>
        <h1>投资组合</h1>
        <p>
          以加权平均成本维护持仓，通过不可变买卖记录同步投资账户现金与已实现收益。
        </p>
      </div>
      <a-space>
        <a-button size="large" @click="openSnapshot()">
          <LineChartOutlined />发布行情
        </a-button>
        <a-button type="primary" size="large" @click="openCreateHolding">
          <PlusOutlined />添加持仓
        </a-button>
      </a-space>
    </div>

    <section class="portfolio-hero">
      <div>
        <span>PORTFOLIO MARKET VALUE</span>
        <strong class="sensitive-amount">{{
          formatMoney(portfolio?.total_market_value, currency)
        }}</strong>
        <small>市场数据不完整时总市值显示为未知，而不是错误地显示为零。</small>
      </div>
      <div class="portfolio-metrics">
        <span>总成本<strong class="sensitive-amount">{{
          formatMoney(portfolio?.total_cost_value, currency)
        }}</strong></span>
        <span>
          未实现收益
          <strong
            class="sensitive-amount"
            :class="
              toNumber(portfolio?.total_unrealized_gain) >= 0
                ? 'money-positive'
                : 'money-negative'
            "
          >
            {{ formatMoney(portfolio?.total_unrealized_gain, currency) }}
          </strong>
        </span>
        <span>持仓数量<strong>{{ portfolio?.holdings.length ?? 0 }}</strong></span>
      </div>
      <a-select
        v-model:value="currency"
        class="portfolio-currency"
        @change="loadData"
      >
        <a-select-option value="CNY">CNY</a-select-option>
        <a-select-option value="USD">USD</a-select-option>
        <a-select-option value="HKD">HKD</a-select-option>
      </a-select>
    </section>

    <a-card class="surface-card investment-card" :bordered="false">
      <a-tabs v-model:active-key="activeTab">
        <a-tab-pane key="portfolio" tab="组合表现">
          <a-spin :spinning="loading">
            <div v-if="portfolio?.holdings.length" class="performance-grid">
              <article
                v-for="item in portfolio.holdings"
                :key="item.holding_id"
                class="performance-item"
              >
                <header>
                  <div class="symbol-mark">{{ item.symbol.slice(0, 2) }}</div>
                  <div>
                    <strong>{{ item.symbol }}</strong><span>持仓表现</span>
                  </div>
                  <RiseOutlined
                    :class="
                      toNumber(item.unrealized_gain) >= 0
                        ? 'money-positive'
                        : 'money-negative'
                    "
                  />
                </header>
                <div class="performance-value">
                  <span>市场价值</span>
                  <strong class="sensitive-amount">{{
                    formatMoney(item.market_value, currency)
                  }}</strong>
                </div>
                <dl>
                  <div>
                    <dt>数量</dt>
                    <dd>{{ formatNumber(item.quantity, 6) }}</dd>
                  </div>
                  <div>
                    <dt>当前价</dt>
                    <dd class="sensitive-amount">
                      {{ formatMoney(item.current_price, currency) }}
                    </dd>
                  </div>
                  <div>
                    <dt>浮动收益</dt>
                    <dd
                      class="sensitive-amount"
                      :class="
                        toNumber(item.unrealized_gain) >= 0
                          ? 'money-positive'
                          : 'money-negative'
                      "
                    >
                      {{ formatMoney(item.unrealized_gain, currency) }}
                    </dd>
                  </div>
                </dl>
                <small>价格时间
                  {{ formatDate(item.price_recorded_at, "MM-DD HH:mm") }}</small>
              </article>
            </div>
            <a-empty v-else description="当前币种暂无可估值持仓" />
          </a-spin>
        </a-tab-pane>

        <a-tab-pane key="holdings" tab="持仓管理">
          <a-table
            :columns="holdingColumns"
            :data-source="holdings"
            :loading="loading"
            :pagination="false"
            :scroll="{ x: 900 }"
            row-key="id"
          >
            <template
              #bodyCell="{
                column,
                record,
              }: {
                column: { key: string };
                record: Holding;
              }"
            >
              <template v-if="column.key === 'symbol'">
                <div class="holding-symbol">
                  <div>{{ record.symbol.slice(0, 2) }}</div>
                  <span><strong>{{ record.symbol }}</strong><small>{{
                    assetTypeLabels[record.asset_type]
                  }}</small></span>
                </div>
              </template>
              <template v-else-if="column.key === 'account'">
                {{
                  accounts.find((item) => item.id === record.account_id)
                    ?.name ?? "未知账户"
                }}
              </template>
              <template v-else-if="column.key === 'quantity'">
                {{ formatNumber(record.quantity, 6) }}
              </template>
              <template v-else-if="column.key === 'cost_basis'">
                <span class="sensitive-amount">{{
                  formatMoney(record.cost_basis, record.currency)
                }}</span>
              </template>
              <template v-else-if="column.key === 'cost_value'">
                <strong class="sensitive-amount">{{
                  formatMoney(
                    toNumber(record.quantity) * toNumber(record.cost_basis),
                    record.currency,
                  )
                }}</strong>
              </template>
              <template v-else-if="column.key === 'actions'">
                <a-space>
                  <a-button
                    type="link"
                    class="table-action"
                    @click="openTrade(record)"
                  >
                    <SwapOutlined />交易
                  </a-button>
                  <a-dropdown>
                    <a-button type="link" class="table-action">更多</a-button>
                    <template #overlay>
                      <a-menu>
                        <a-menu-item @click="openEditHolding(record)">
                          <EditOutlined />修正
                        </a-menu-item>
                        <a-menu-item @click="openSnapshot(record)">
                          <BarChartOutlined />发布价格
                        </a-menu-item>
                        <a-menu-item danger @click="deleteHolding(record)">
                          <DeleteOutlined />删除
                        </a-menu-item>
                      </a-menu>
                    </template>
                  </a-dropdown>
                </a-space>
              </template>
            </template>
            <template #emptyText><a-empty description="暂无持仓" /></template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="trades" tab="交易历史">
          <a-table
            :columns="tradeColumns"
            :data-source="trades"
            :loading="loading"
            :pagination="{ pageSize: 20 }"
            :scroll="{ x: 860 }"
            row-key="id"
          >
            <template
              #bodyCell="{
                column,
                record,
              }: {
                column: { key: string };
                record: InvestmentTransaction;
              }"
            >
              <template v-if="column.key === 'time'">
                {{ formatDate(record.transaction_at, "YYYY-MM-DD HH:mm") }}
              </template>
              <template v-else-if="column.key === 'symbol'">
                {{ holdingMap.get(record.holding_id)?.symbol ?? "—" }}
              </template>
              <template v-else-if="column.key === 'type'">
                <a-tag
                  :color="record.transaction_type === 'buy' ? 'blue' : 'orange'"
                >
                  {{ record.transaction_type === "buy" ? "买入" : "卖出" }}
                </a-tag>
              </template>
              <template v-else-if="column.key === 'quantity'">
                {{ formatNumber(record.quantity, 6) }}
              </template>
              <template v-else-if="column.key === 'price'">
                <span class="sensitive-amount">{{
                  formatMoney(record.price, record.currency)
                }}</span>
              </template>
              <template v-else-if="column.key === 'fee'">
                <span class="sensitive-amount">{{
                  formatMoney(record.fee, record.currency)
                }}</span>
              </template>
              <template v-else-if="column.key === 'gain'">
                <strong
                  class="sensitive-amount"
                  :class="
                    toNumber(record.realized_gain) >= 0
                      ? 'money-positive'
                      : 'money-negative'
                  "
                >
                  {{ formatMoney(record.realized_gain, record.currency) }}
                </strong>
              </template>
            </template>
            <template #emptyText>
              <a-empty description="暂无投资交易" />
            </template>
          </a-table>
        </a-tab-pane>
      </a-tabs>
    </a-card>

    <a-modal
      v-model:open="holdingModalOpen"
      :title="editingHolding ? '修正持仓' : '添加期初持仓'"
      :confirm-loading="saving"
      ok-text="保存持仓"
      cancel-text="取消"
      @ok="saveHolding"
    >
      <a-form layout="vertical" :model="holdingForm">
        <a-form-item label="投资账户" required>
          <a-select
            v-model:value="holdingForm.account_id"
            :disabled="Boolean(editingHolding)"
            placeholder="选择投资账户"
            @change="syncHoldingCurrency"
          >
            <a-select-option
              v-for="account in investmentAccounts"
              :key="account.id"
              :value="account.id"
            >
              {{ account.name }} · {{ account.currency }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <div class="form-grid">
          <a-form-item label="证券代码" required>
            <a-input
              v-model:value="holdingForm.symbol"
              :disabled="Boolean(editingHolding)"
              placeholder="例如：AAPL"
            />
          </a-form-item>
          <a-form-item label="资产类型" required>
            <a-select v-model:value="holdingForm.asset_type">
              <a-select-option
                v-for="(label, value) in assetTypeLabels"
                :key="value"
                :value="value"
              >
                {{ label }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </div>
        <div class="form-grid">
          <a-form-item label="持仓数量" required>
            <a-input-number
              v-model:value="holdingForm.quantity"
              :min="0"
              :precision="6"
              style="width: 100%"
            />
          </a-form-item>
          <a-form-item label="平均单位成本" required>
            <a-input-number
              v-model:value="holdingForm.cost_basis"
              :min="0"
              :precision="4"
              style="width: 100%"
            />
          </a-form-item>
        </div>
        <a-alert
          type="warning"
          show-icon
          :message="
            editingHolding
              ? '存在投资交易后，后端将禁止直接修正数量和平均成本。'
              : '期初持仓不会生成虚构买入记录，后续变化请通过投资交易登记。'
          "
        />
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="tradeModalOpen"
      :title="`${selectedHolding?.symbol ?? ''} · 登记交易`"
      :confirm-loading="saving"
      ok-text="确认交易"
      cancel-text="取消"
      @ok="saveTrade"
    >
      <a-form layout="vertical" :model="tradeForm">
        <a-form-item label="交易方向">
          <a-segmented
            v-model:value="tradeForm.transaction_type"
            :options="[
              { label: '买入', value: 'buy' },
              { label: '卖出', value: 'sell' },
            ]"
            block
          />
        </a-form-item>
        <div class="form-grid">
          <a-form-item label="数量" required>
            <a-input-number
              v-model:value="tradeForm.quantity"
              :min="0.000001"
              :precision="6"
              style="width: 100%"
            />
          </a-form-item>
          <a-form-item label="成交单价" required>
            <a-input-number
              v-model:value="tradeForm.price"
              :min="0"
              :precision="4"
              style="width: 100%"
            />
          </a-form-item>
        </div>
        <div class="form-grid">
          <a-form-item label="手续费">
            <a-input-number
              v-model:value="tradeForm.fee"
              :min="0"
              :precision="4"
              style="width: 100%"
            />
          </a-form-item>
          <a-form-item label="成交时间" required>
            <a-date-picker
              v-model:value="tradeForm.transaction_at"
              show-time
              style="width: 100%"
            />
          </a-form-item>
        </div>
        <a-alert
          type="info"
          show-icon
          message="买入采用含手续费的加权平均成本；卖出不会改变剩余持仓平均成本，并会校验超卖。"
        />
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="snapshotModalOpen"
      title="发布市场价格快照"
      :confirm-loading="saving"
      ok-text="发布价格"
      cancel-text="取消"
      @ok="saveSnapshot"
    >
      <a-form layout="vertical" :model="snapshotForm">
        <div class="form-grid">
          <a-form-item label="证券代码" required>
            <a-input v-model:value="snapshotForm.symbol" />
          </a-form-item>
          <a-form-item label="资产类型" required>
            <a-select v-model:value="snapshotForm.asset_type">
              <a-select-option
                v-for="(label, value) in assetTypeLabels"
                :key="value"
                :value="value"
              >
                {{ label }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </div>
        <div class="form-grid">
          <a-form-item label="价格" required>
            <a-input-number
              v-model:value="snapshotForm.price"
              :min="0"
              :precision="4"
              style="width: 100%"
            />
          </a-form-item>
          <a-form-item label="币种" required>
            <a-select v-model:value="snapshotForm.currency">
              <a-select-option value="CNY">CNY</a-select-option>
              <a-select-option value="USD">USD</a-select-option>
              <a-select-option value="HKD">HKD</a-select-option>
            </a-select>
          </a-form-item>
        </div>
        <a-form-item label="价格时间" required>
          <a-date-picker
            v-model:value="snapshotForm.recorded_at"
            show-time
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="数据来源" required>
          <a-input
            v-model:value="snapshotForm.data_source"
            placeholder="例如：manual、provider-name"
          />
        </a-form-item>
        <a-alert
          type="info"
          show-icon
          message="行情快照作为只追加参考数据保存，发布后不可修改。"
        />
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.portfolio-hero {
  position: relative;
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  align-items: end;
  gap: 32px;
  min-height: 180px;
  padding: 30px;
  border: 1px solid var(--line);
  border-radius: 14px;
  color: var(--ink-950);
  background: #ffffff;
  overflow: hidden;
}

.portfolio-hero > div:first-child {
  display: grid;
}

.portfolio-hero > div:first-child span {
  color: var(--ink-500);
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.16em;
}

.portfolio-hero > div:first-child strong {
  margin: 8px 0;
  font-family: inherit;
  font-size: clamp(28px, 4vw, 42px);
  font-weight: 500;
}

.portfolio-hero small {
  color: var(--ink-500);
  font-size: 10px;
}

.portfolio-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.portfolio-metrics span {
  display: grid;
  color: var(--ink-500);
  font-size: 9px;
}

.portfolio-metrics strong {
  margin-top: 5px;
  color: var(--ink-950);
  font-size: 15px;
}

.portfolio-currency {
  position: absolute;
  top: 22px;
  right: 22px;
  width: 86px;
}

.investment-card {
  overflow: hidden;
}

.performance-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.performance-item {
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #ffffff;
}

.performance-item header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
}

.symbol-mark,
.holding-symbol > div {
  display: grid;
  width: 38px;
  height: 38px;
  border-radius: 11px;
  color: #8d6920;
  background: #f7edcf;
  font-family: "Iowan Old Style", serif;
  font-size: 12px;
  font-weight: 700;
  place-items: center;
}

.performance-item header > div:nth-child(2),
.holding-symbol > span {
  display: grid;
}

.performance-item header strong,
.holding-symbol strong {
  color: var(--ink-950);
  font-size: 12px;
}

.performance-item header span,
.holding-symbol small {
  color: var(--ink-500);
  font-size: 9px;
}

.performance-value {
  display: grid;
  margin: 24px 0 18px;
}

.performance-value span {
  color: var(--ink-500);
  font-size: 9px;
}

.performance-value strong {
  color: var(--ink-950);
  font-family: "Iowan Old Style", Georgia, serif;
  font-size: 24px;
}

.performance-item dl {
  display: grid;
  gap: 8px;
  margin: 0 0 14px;
}

.performance-item dl div {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
}

.performance-item dt {
  color: var(--ink-500);
}

.performance-item dd {
  margin: 0;
  color: var(--ink-900);
  font-weight: 650;
}

.performance-item > small {
  color: #9aaba7;
  font-size: 8px;
}

.holding-symbol {
  display: flex;
  align-items: center;
  gap: 10px;
}

.holding-symbol > div {
  width: 34px;
  height: 34px;
  border-radius: 10px;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

@media (max-width: 1050px) {
  .performance-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .portfolio-hero {
    grid-template-columns: 1fr;
  }

  .portfolio-metrics {
    grid-template-columns: 1fr;
  }

  .performance-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
