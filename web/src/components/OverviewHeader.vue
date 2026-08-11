<script setup lang="ts">
import dayjs from 'dayjs'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

withDefaults(
  defineProps<{
    subtitle?: string
    compact?: boolean
  }>(),
  {
    subtitle: '',
    compact: false,
  },
)

const route = useRoute()
const auth = useAuthStore()

const greeting = computed(() => {
  const hour = dayjs().hour()
  if (hour < 11) return '早上好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

const activeTab = computed(() => (route.name === 'accounts' ? 'accounts' : 'overview'))
</script>

<template>
  <header class="overview-header" :class="{ 'is-compact': compact }">
    <div class="overview-heading-row">
      <div>
        <span v-if="!compact" class="overview-kicker">FINANCIAL OVERVIEW</span>
        <h1>{{ greeting }}，{{ auth.user?.username }}</h1>
        <p v-if="!compact && subtitle">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="overview-actions">
        <slot name="actions" />
      </div>
    </div>

    <nav class="overview-tabs" aria-label="首页视图">
      <router-link
        to="/"
        :class="{ active: activeTab === 'overview' }"
        :aria-current="activeTab === 'overview' ? 'page' : undefined"
      >
        概览
      </router-link>
      <router-link
        to="/accounts"
        :class="{ active: activeTab === 'accounts' }"
        :aria-current="activeTab === 'accounts' ? 'page' : undefined"
      >
        净资产
      </router-link>
    </nav>
  </header>
</template>

<style scoped>
.overview-header {
  display: grid;
  gap: 14px;
  min-height: 108px;
  padding: 2px 2px 0;
  border-bottom: 1px solid #eeeeef;
}

.overview-header.is-compact {
  gap: 10px;
  min-height: 82px;
  padding-top: 0;
}

.overview-header.is-compact .overview-heading-row h1 {
  margin: 0;
  font-size: clamp(20px, 1.7vw, 24px);
}

.overview-heading-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.overview-kicker {
  color: var(--ink-500);
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.overview-heading-row h1 {
  margin: 6px 0 3px;
  color: var(--ink-950);
  font-size: clamp(20px, 2vw, 26px);
  font-weight: 500;
  letter-spacing: -0.025em;
  line-height: 1.2;
}

.overview-heading-row p {
  max-width: 680px;
  margin: 0;
  color: var(--ink-500);
  font-size: 10px;
  line-height: 1.55;
}

.overview-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.overview-tabs {
  display: flex;
  align-items: flex-end;
  align-self: end;
  gap: 4px;
}

.overview-tabs a {
  position: relative;
  display: grid;
  min-width: 74px;
  height: 38px;
  padding: 0 14px;
  border-radius: 7px 7px 0 0;
  color: #77777e;
  font-size: 11px;
  place-items: center;
  text-decoration: none;
}

.overview-tabs a:hover {
  color: #29292d;
  background: #f7f7f8;
}

.overview-tabs a.active {
  color: #1f1f23;
  background: #f2f2f3;
  font-weight: 600;
}

.overview-tabs a.active::after {
  position: absolute;
  right: 14px;
  bottom: -1px;
  left: 14px;
  height: 2px;
  border-radius: 2px 2px 0 0;
  background: #8178ff;
  content: '';
}

@media (max-width: 700px) {
  .overview-header {
    gap: 16px;
  }

  .overview-heading-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .overview-actions {
    width: 100%;
  }

  .overview-actions :deep(.ant-btn) {
    flex: 1;
  }
}
</style>
