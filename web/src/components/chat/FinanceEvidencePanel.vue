<script setup lang="ts">
import dayjs from 'dayjs'

import type { MessageEvidence } from '@/types/chat'

withDefaults(
  defineProps<{
    evidence?: MessageEvidence[]
    dataAsOf?: string | null
    riskNotice?: string | null
  }>(),
  {
    evidence: () => [],
    dataAsOf: null,
    riskNotice: null,
  },
)

function evidencePeriod(item: MessageEvidence): string {
  if (item.period_start && item.period_end) {
    return `${item.period_start} 至 ${item.period_end}`
  }
  return '当前快照'
}

function formatDataTime(value: string): string {
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}
</script>

<template>
  <section v-if="evidence.length" class="finance-evidence">
    <header>
      <span>个人财务数据</span>
      <time v-if="dataAsOf">数据更新 {{ formatDataTime(dataAsOf) }}</time>
    </header>
    <article
      v-for="item in evidence"
      :key="item.evidence_id"
      class="evidence-card"
    >
      <div class="evidence-heading">
        <strong>{{ item.label }}</strong>
        <code>{{ item.tool_name }}</code>
      </div>
      <p class="evidence-meta">
        {{ evidencePeriod(item) }}
        <template v-if="item.currencies.length">
          · {{ item.currencies.join(' / ') }}
        </template>
        · 数据时间 {{ formatDataTime(item.data_as_of) }}
      </p>
      <div v-if="item.facts.length" class="evidence-facts">
        <span
          v-for="(fact, index) in item.facts.slice(0, 8)"
          :key="`${fact.label}-${fact.context}-${index}`"
        >
          <small v-if="fact.context">{{ fact.context }}</small>
          {{ fact.label }}：{{ fact.value }}
          {{ fact.currency ?? '' }}
        </span>
      </div>
      <p class="calculation-basis">口径：{{ item.calculation_basis }}</p>
      <p v-if="item.warning_codes.length" class="evidence-warning">
        数据提示：{{ item.warning_codes.join('、') }}
      </p>
    </article>
  </section>
  <aside v-if="riskNotice" class="risk-notice">
    <strong>风险提示</strong>
    <p>{{ riskNotice }}</p>
  </aside>
</template>

<style scoped>
.finance-evidence {
  display: grid;
  gap: 9px;
  margin: 0 0 16px;
}

.finance-evidence > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--ink-500);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.08em;
}

.finance-evidence time {
  font-weight: 500;
  letter-spacing: normal;
}

.evidence-card {
  padding: 12px 13px;
  border: 1px solid rgb(15 118 110 / 16%);
  border-radius: 11px;
  background: linear-gradient(135deg, #f6fbf8, #fbfcf8);
}

.evidence-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.evidence-heading strong {
  color: var(--ink-900);
  font-size: 13px;
}

.evidence-heading code {
  color: var(--mint-700);
  font-size: 10px;
}

.evidence-meta,
.calculation-basis,
.evidence-warning {
  margin: 6px 0 0;
  color: var(--ink-500);
  font-size: 11px;
  line-height: 1.6;
}

.evidence-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 9px;
}

.evidence-facts span {
  padding: 4px 7px;
  border-radius: 7px;
  color: var(--ink-800);
  background: rgb(255 255 255 / 80%);
  font-size: 11px;
}

.evidence-facts small {
  margin-right: 4px;
  color: var(--mint-700);
}

.evidence-warning {
  color: #9a6b17;
}

.risk-notice {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid rgb(184 124 26 / 22%);
  border-radius: 10px;
  color: #795718;
  background: #fff9ed;
}

.risk-notice strong {
  font-size: 11px;
  letter-spacing: 0.06em;
}

.risk-notice p {
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.7;
}
</style>
