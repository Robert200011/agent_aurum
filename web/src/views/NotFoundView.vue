<script setup lang="ts">
import { CompassOutlined } from '@ant-design/icons-vue'
</script>

<template>
  <main class="not-found">
    <div class="not-found-mark"><CompassOutlined /></div>
    <span>404 · LOST LEDGER</span>
    <h1>这个页面不在账本里</h1>
    <p>你访问的地址不存在，或已经被移动到新的位置。</p>
    <router-link to="/">
      <a-button type="primary" size="large">返回财务总览</a-button>
    </router-link>
  </main>
</template>

<style scoped>
.not-found {
  display: grid;
  min-height: 100vh;
  padding: 32px;
  color: var(--ink-900);
  background: var(--paper);
  text-align: center;
  place-content: center;
  justify-items: center;
}

.not-found-mark {
  display: grid;
  width: 72px;
  height: 72px;
  margin-bottom: 20px;
  border-radius: 24px;
  color: var(--mint-700);
  background: var(--mint-100);
  font-size: 32px;
  place-items: center;
}

.not-found > span {
  color: var(--gold-500);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.not-found h1 {
  margin: 12px 0;
  font-family: 'Iowan Old Style', 'Songti SC', serif;
  font-size: 42px;
}

.not-found p {
  margin: 0 0 28px;
  color: var(--ink-500);
}
</style>
