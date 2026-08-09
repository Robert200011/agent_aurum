<script setup lang="ts">
withDefaults(
  defineProps<{
    compact?: boolean;
    inverse?: boolean;
  }>(),
  {
    compact: false,
    inverse: false,
  },
);
</script>

<template>
  <div class="brand" :class="{ compact, inverse }">
    <svg class="brand-mark" viewBox="0 0 44 44" aria-hidden="true">
      <path class="brand-orbit" d="M5 25C8 10 22 4 34 12c11 7 8 23-4 28" />
      <path
        class="brand-rays"
        d="m22 3 1 6M8 9l5 5M3 23l7-1M9 36l5-6m16-20 4-5m1 28 5 3"
      />
      <path
        class="brand-sun"
        d="M15 19c3-7 12-8 16-2 5 7 0 15-8 15-7 0-11-7-8-13Z"
      />
    </svg>
    <div v-if="!compact" class="brand-copy">
      <strong>Aurum</strong>
      <small>PERSONAL FINANCE, IN FOCUS</small>
    </div>
  </div>
</template>

<style scoped>
.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--graphite-900, var(--ink-950));
}

.brand.inverse {
  color: white;
}

.brand-mark {
  width: 42px;
  height: 42px;
  fill: none;
  stroke: var(--orange-600, #c96f45);
  stroke-linecap: round;
  stroke-linejoin: round;
}

.brand-orbit {
  stroke-width: 1.35;
  opacity: 0.72;
}

.brand-rays {
  stroke-width: 1.8;
}

.brand-sun {
  fill: var(--orange-400, #efa46b);
  fill-opacity: 0.18;
  stroke-width: 2;
}

.brand-copy {
  display: grid;
  gap: 1px;
}

.brand-copy strong {
  font-family: "Iowan Old Style", Georgia, serif;
  font-size: 27px;
  font-weight: 700;
  letter-spacing: -0.015em;
  line-height: 1;
}

.brand-copy small {
  color: currentColor;
  font-size: 7px;
  font-weight: 700;
  letter-spacing: 0.15em;
  opacity: 0.62;
}

.compact .brand-mark {
  width: 36px;
  height: 36px;
}

.inverse .brand-mark {
  stroke: #f4c7a1;
}

.inverse .brand-sun {
  fill: #efa46b;
}
</style>
