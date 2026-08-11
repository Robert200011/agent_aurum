<script setup lang="ts">
import {
  BarChartOutlined,
  CloseOutlined,
  DashboardOutlined,
  LockOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  PieChartOutlined,
  SwapOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import BrandMark from '@/components/BrandMark.vue'
import ChatView from '@/views/ChatView.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const collapsed = ref(false)
const mobileOpen = ref(false)
const isMobile = ref(false)
const loggingOut = ref(false)
const logoutConfirmOpen = ref(false)
const userMenuOpen = ref(false)
const agentOpen = ref(false)
const agentHasOpened = ref(false)

const selectedKeys = computed(() => {
  const segments = route.path.split('/').filter(Boolean)
  const activeSection = segments[0] || 'dashboard'
  return [activeSection === 'accounts' ? 'dashboard' : activeSection]
})

const pageTitle = computed(() => String(route.meta.title ?? 'Aurum Agent'))

function updateViewport(): void {
  isMobile.value = window.innerWidth < 900
  if (isMobile.value) collapsed.value = true
}

function navigate(key: string): void {
  mobileOpen.value = false
  if (key === 'chat') {
    toggleAgent()
    return
  }
  void router.push(key === 'dashboard' ? '/' : `/${key}`)
}

function toggleAgent(): void {
  agentHasOpened.value = true
  agentOpen.value = !agentOpen.value
}

function handleGlobalKeydown(event: KeyboardEvent): void {
  if (event.key === '/' && event.ctrlKey) {
    event.preventDefault()
    toggleAgent()
  }
}

async function handleUserMenu(event: { key: string }): Promise<void> {
  userMenuOpen.value = false

  if (event.key === 'password') {
    await router.push('/change-password')
    return
  }

  if (event.key === 'logout' && !loggingOut.value) {
    logoutConfirmOpen.value = true
  }
}

async function confirmLogout(): Promise<void> {
  if (loggingOut.value) return

  loggingOut.value = true
  logoutConfirmOpen.value = false
  const logoutRequest = auth.logout()
  try {
    // logout() 会同步清除本地身份，因此路由可以立即进入登录页。
    await router.replace('/login')
  } finally {
    await logoutRequest
    loggingOut.value = false
  }
}

onMounted(() => {
  updateViewport()
  window.addEventListener('resize', updateViewport)
  window.addEventListener('keydown', handleGlobalKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateViewport)
  window.removeEventListener('keydown', handleGlobalKeydown)
})
</script>

<template>
  <a-layout class="app-layout">
    <a-layout-sider
      v-if="!isMobile"
      v-model:collapsed="collapsed"
      :width="220"
      :collapsed-width="64"
      :trigger="null"
      class="app-sider"
    >
      <div class="sider-brand">
        <BrandMark :compact="collapsed" />
      </div>
      <span v-if="!collapsed" class="nav-section-label">财务</span>
      <a-menu
        mode="inline"
        :selected-keys="selectedKeys"
        class="nav-menu"
        @click="({ key }: { key: string }) => navigate(key)"
      >
        <a-menu-item key="dashboard">
          <DashboardOutlined />
          <span>首页</span>
        </a-menu-item>
        <a-menu-item key="transactions">
          <SwapOutlined />
          <span>收支明细</span>
        </a-menu-item>
        <a-menu-item key="budgets">
          <PieChartOutlined />
          <span>预算管理</span>
        </a-menu-item>
        <a-menu-item key="investments">
          <BarChartOutlined />
          <span>个人投资</span>
        </a-menu-item>
      </a-menu>
      <button
        type="button"
        class="assistant-entry"
        :class="{ 'is-active': agentOpen }"
        aria-label="打开智能问答"
        :aria-expanded="agentOpen"
        @click="toggleAgent"
      >
        <svg class="assistant-spark" viewBox="0 0 20 20" aria-hidden="true">
          <path
            d="M10 1c.7 5.6 3.4 8.3 9 9-5.6.7-8.3 3.4-9 9-.7-5.6-3.4-8.3-9-9 5.6-.7 8.3-3.4 9-9Z"
          />
        </svg>
        <span v-if="!collapsed">智能问答</span>
        <small v-if="!collapsed">Ctrl /</small>
      </button>
    </a-layout-sider>

    <a-drawer
      v-model:open="mobileOpen"
      placement="left"
      :width="280"
      :closable="false"
      class="mobile-nav-drawer"
    >
      <div class="mobile-brand">
        <BrandMark />
      </div>
      <a-menu
        mode="inline"
        :selected-keys="selectedKeys"
        @click="({ key }: { key: string }) => navigate(key)"
      >
        <a-menu-item key="dashboard"><DashboardOutlined />首页</a-menu-item>
        <a-menu-item key="chat"><MessageOutlined />智能问答</a-menu-item>
        <a-menu-item key="transactions"><SwapOutlined />收支明细</a-menu-item>
        <a-menu-item key="budgets"><PieChartOutlined />预算管理</a-menu-item>
        <a-menu-item key="investments">
          <BarChartOutlined />个人投资
        </a-menu-item>
      </a-menu>
    </a-drawer>

    <a-layout class="main-layout">
      <a-layout-header class="app-header">
        <div class="header-left">
          <a-button
            type="text"
            class="collapse-button"
            :aria-label="isMobile ? '打开导航' : '收起或展开导航'"
            @click="isMobile ? (mobileOpen = true) : (collapsed = !collapsed)"
          >
            <MenuUnfoldOutlined v-if="collapsed || isMobile" />
            <MenuFoldOutlined v-else />
          </a-button>
          <div>
            <span class="header-eyebrow">AURUM WORKSPACE</span>
            <strong>{{ pageTitle }}</strong>
          </div>
        </div>

        <a-dropdown v-model:open="userMenuOpen" placement="bottomRight">
          <button class="user-trigger" type="button">
            <a-avatar :size="36" class="user-avatar">
              <template #icon><UserOutlined /></template>
            </a-avatar>
            <span class="user-copy">
              <strong>{{ auth.user?.username }}</strong>
              <small>个人用户</small>
            </span>
          </button>
          <template #overlay>
            <a-menu @click="handleUserMenu">
              <a-menu-item key="password">
                <LockOutlined />
                修改密码
              </a-menu-item>
              <a-menu-divider />
              <a-menu-item key="logout" :disabled="loggingOut" danger>
                <LogoutOutlined />退出登录
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </a-layout-header>

      <a-layout-content class="app-content">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </a-layout-content>
    </a-layout>

    <transition name="agent-slide">
      <aside
        v-if="agentHasOpened"
        v-show="agentOpen"
        class="agent-drawer"
        aria-label="Aurum AI Agent"
      >
        <header class="agent-drawer-header">
          <span>AI AGENT</span>
          <button type="button" aria-label="关闭智能问答" @click="agentOpen = false">
            <CloseOutlined />
          </button>
        </header>
        <ChatView embedded />
      </aside>
    </transition>

    <a-modal
      v-model:open="logoutConfirmOpen"
      centered
      title="确认退出登录"
      :width="420"
      ok-text="是"
      cancel-text="否"
      :confirm-loading="loggingOut"
      :closable="!loggingOut"
      :keyboard="!loggingOut"
      :mask-closable="!loggingOut"
      :ok-button-props="{ danger: true }"
      :cancel-button-props="{ disabled: loggingOut }"
      @ok="confirmLogout"
    >
      <p class="logout-confirm-copy">
        确定要退出当前账号吗？退出后需要重新登录才能继续使用 Aurum。
      </p>
    </a-modal>
  </a-layout>
</template>

<style scoped>
.app-layout {
  --ink-950: #171719;
  --ink-900: #242428;
  --ink-800: #34343a;
  --ink-700: #5e5e66;
  --ink-500: #8a8a92;
  --mint-700: #4f6ff5;
  --mint-500: #6f83ff;
  --mint-100: #f0f2ff;
  --gold-500: #7676ff;
  --line: #e7e7e9;
  min-height: 100vh;
  background: #ffffff;
}

.app-layout :deep(.ant-btn-primary) {
  border-color: #18181b;
  background: #18181b;
  box-shadow: none;
}

.app-layout :deep(.ant-btn-primary:not(:disabled):hover) {
  border-color: #303036;
  background: #303036;
}

.app-sider {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 20;
  border-right: 1px solid #e8e8ea;
  background: #ffffff;
  box-shadow: none;
}

.sider-brand {
  display: flex;
  align-items: center;
  height: 76px;
  padding: 0 16px;
  --orange-600: #151518;
  --orange-400: #151518;
}

.sider-brand :deep(.brand-mark) {
  width: 34px;
  height: 34px;
}

.sider-brand :deep(.brand-copy strong) {
  font-size: 23px;
}

.sider-brand :deep(.brand-copy small) {
  display: none;
}

.nav-menu {
  padding: 4px 10px;
  background: transparent;
  border: 0;
}

.nav-menu :deep(.ant-menu-item) {
  height: 38px;
  margin: 3px 0;
  padding-inline: 12px !important;
  border-radius: 7px;
  color: #66666d;
  font-size: 12px;
}

.nav-menu :deep(.ant-menu-item-selected) {
  color: #171719;
  background: #eeeeef;
  box-shadow: none;
}

.nav-menu :deep(.ant-menu-item .anticon) {
  font-size: 14px;
}

.nav-section-label {
  display: block;
  padding: 12px 22px 4px;
  color: #a3a3a9;
  font-size: 8px;
  font-weight: 650;
  letter-spacing: 0.12em;
}

.nav-menu :deep(.ant-menu-item-group-title) {
  padding: 18px 12px 4px;
  color: #a3a3a9;
  font-size: 8px;
  font-weight: 650;
  letter-spacing: 0.12em;
}

.assistant-entry {
  position: absolute;
  right: 10px;
  bottom: 14px;
  left: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  width: auto !important;
  height: 44px;
  padding: 0 12px;
  border: 1px solid #ededee;
  border-radius: 9px;
  color: #7168f5;
  background: #ffffff;
  box-shadow: 0 2px 8px rgb(24 24 27 / 3%);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.assistant-entry:hover,
.assistant-entry.is-active {
  border-color: #e8e5ff;
  background: #faf9ff;
}

.agent-drawer {
  position: fixed;
  inset: 0 0 0 auto;
  z-index: 50;
  display: flex;
  width: min(390px, calc(100vw - 64px));
  border-left: 1px solid #dedee2;
  background: #ffffff;
  box-shadow: -18px 0 48px rgb(24 24 27 / 8%);
  flex-direction: column;
}

.agent-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 54px;
  padding: 0 13px 0 18px;
  border-bottom: 1px solid #ececee;
  flex: 0 0 54px;
}

.agent-drawer-header span {
  color: #6f6f76;
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.2em;
}

.agent-drawer-header button {
  display: grid;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 0;
  border-radius: 7px;
  color: #85858c;
  background: transparent;
  cursor: pointer;
  place-items: center;
}

.agent-drawer-header button:hover {
  color: #202024;
  background: #f3f3f4;
}

.agent-slide-enter-active,
.agent-slide-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.24s ease;
}

.agent-slide-enter-from,
.agent-slide-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

.assistant-spark {
  width: 14px;
  height: 14px;
  flex: 0 0 14px;
  fill: #8178ff;
}

.assistant-entry small {
  margin-left: auto;
  color: #a8a8ae;
  font-size: 9px;
}

.ant-layout-sider-collapsed .assistant-entry {
  justify-content: center;
  padding: 0;
}

.main-layout {
  min-width: 0;
  margin-left: 220px;
  background: #ffffff;
  transition: margin-left 0.2s;
}

.ant-layout-sider-collapsed + .main-layout {
  margin-left: 64px;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 12;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  padding: 0 28px;
  border-bottom: 1px solid #ececee;
  background: rgb(255 255 255 / 94%);
  backdrop-filter: blur(14px);
  line-height: normal;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.collapse-button {
  display: grid;
  width: 32px;
  min-width: 32px;
  height: 32px;
  padding: 0;
  color: var(--ink-700);
  font-size: 18px;
  place-items: center;
}

.header-left > div:last-child {
  display: grid;
  align-content: center;
  gap: 3px;
  line-height: 1;
}

.header-left strong {
  color: var(--ink-950);
  font-size: 15px;
  line-height: 1.2;
}

.header-eyebrow {
  color: var(--ink-500);
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.18em;
  line-height: 1.2;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 44px;
  padding: 4px 6px;
  border: 0;
  border-radius: 12px;
  color: var(--ink-900);
  background: transparent;
  cursor: pointer;
  line-height: 1;
}

.user-trigger:hover {
  background: #f4f4f5;
}

.user-avatar {
  flex: 0 0 auto;
  color: #2d2d31;
  background: #ececee;
}

.user-copy {
  display: grid;
  align-content: center;
  gap: 3px;
  min-width: 76px;
  line-height: 1;
  text-align: left;
}

.user-copy strong {
  font-size: 13px;
  line-height: 1.2;
}

.user-copy small {
  color: var(--ink-500);
  font-size: 10px;
  line-height: 1.2;
}

.app-content {
  min-height: calc(100vh - 64px);
  padding: 28px;
  background: #ffffff;
}

.logout-confirm-copy {
  margin: 6px 0 0;
  color: var(--ink-700);
  line-height: 1.7;
}

.mobile-brand {
  padding: 8px 12px 24px;
}

.page-fade-enter-active,
.page-fade-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.page-fade-enter-from,
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

@media (max-width: 900px) {
  .main-layout {
    margin-left: 0;
  }

  .app-header {
    padding: 0 16px;
  }

  .app-content {
    padding: 20px 16px 30px;
  }
}

@media (max-width: 520px) {
  .agent-drawer {
    width: 100vw;
  }

  .user-copy {
    display: none;
  }

  .header-eyebrow {
    display: none;
  }
}
</style>
