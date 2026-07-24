<script setup lang="ts">
withDefaults(
  defineProps<{
    compact?: boolean
    inverse?: boolean
  }>(),
  {
    compact: false,
    inverse: false,
  },
)
</script>

<template>
  <div class="brand" :class="{ compact, inverse }">
    <div class="brand-mark" aria-hidden="true">
      <span />
      <span />
      <span />
    </div>
    <div v-if="!compact" class="brand-copy">
      <strong>Aurum</strong>
      <small>FINANCIAL INTELLIGENCE</small>
    </div>
  </div>
</template>

<style scoped>
.brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  color: var(--ink-950);
}

.brand.inverse {
  color: white;
}

.brand-mark {
  position: relative;
  width: 38px;
  height: 38px;
  border: 1px solid rgb(213 162 63 / 65%);
  border-radius: 12px;
  background: linear-gradient(145deg, #f4d895, #c9912d);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 55%);
  overflow: hidden;
}

.brand-mark span {
  position: absolute;
  left: 9px;
  width: 19px;
  height: 3px;
  border-radius: 4px;
  background: #0b302c;
  transform: rotate(-14deg);
}

.brand-mark span:nth-child(1) {
  top: 11px;
}

.brand-mark span:nth-child(2) {
  top: 18px;
  width: 15px;
}

.brand-mark span:nth-child(3) {
  top: 25px;
  width: 11px;
}

.brand-copy {
  display: grid;
  gap: 1px;
}

.brand-copy strong {
  font-family: 'Iowan Old Style', Georgia, serif;
  font-size: 23px;
  font-weight: 650;
  letter-spacing: 0.01em;
  line-height: 1;
}

.brand-copy small {
  color: currentColor;
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.18em;
  opacity: 0.58;
}

.compact .brand-mark {
  width: 34px;
  height: 34px;
}
</style>
