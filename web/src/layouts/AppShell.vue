<script setup lang="ts">
import {
  BankOutlined,
  BarChartOutlined,
  DashboardOutlined,
  LockOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PieChartOutlined,
  SwapOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import BrandMark from '@/components/BrandMark.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const collapsed = ref(false)
const mobileOpen = ref(false)
const isMobile = ref(false)

const selectedKeys = computed(() => {
  const topLevel = route.path.split('/')[1]
  return [topLevel || 'dashboard']
})

const pageTitle = computed(() => String(route.meta.title ?? 'Aurum Agent'))

function updateViewport(): void {
  isMobile.value = window.innerWidth < 900
  if (isMobile.value) collapsed.value = true
}

function navigate(key: string): void {
  mobileOpen.value = false
  void router.push(key === 'dashboard' ? '/' : `/${key}`)
}

async function handleUserMenu(event: { key: string }): Promise<void> {
  if (event.key === 'password') {
    await router.push('/change-password')
  }
  if (event.key === 'logout') {
    await auth.logout()
    await router.replace('/login')
  }
}

onMounted(() => {
  updateViewport()
  window.addEventListener('resize', updateViewport)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateViewport)
})
</script>

<template>
  <a-layout class="app-layout">
    <a-layout-sider
      v-if="!isMobile"
      v-model:collapsed="collapsed"
      :width="244"
      :collapsed-width="76"
      :trigger="null"
      class="app-sider"
    >
      <div class="sider-brand">
        <BrandMark :compact="collapsed" inverse />
      </div>
      <a-menu
        mode="inline"
        theme="dark"
        :selected-keys="selectedKeys"
        class="nav-menu"
        @click="({ key }: { key: string }) => navigate(key)"
      >
        <a-menu-item key="dashboard">
          <DashboardOutlined />
          <span>财务总览</span>
        </a-menu-item>
        <a-menu-item key="accounts">
          <BankOutlined />
          <span>账户管理</span>
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
          <span>投资组合</span>
        </a-menu-item>
      </a-menu>
      <div v-if="!collapsed" class="sider-note">
        <span>数据边界</span>
        <strong>单币种 · 确定性计算</strong>
        <p>财务结果来自结构化账本，不使用模型猜测。</p>
      </div>
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
        <a-menu-item key="dashboard"><DashboardOutlined />财务总览</a-menu-item>
        <a-menu-item key="accounts"><BankOutlined />账户管理</a-menu-item>
        <a-menu-item key="transactions"><SwapOutlined />收支明细</a-menu-item>
        <a-menu-item key="budgets"><PieChartOutlined />预算管理</a-menu-item>
        <a-menu-item key="investments"><BarChartOutlined />投资组合</a-menu-item>
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

        <a-dropdown placement="bottomRight">
          <button class="user-trigger" type="button">
            <a-avatar :size="36" class="user-avatar">
              <template #icon><UserOutlined /></template>
            </a-avatar>
            <span class="user-copy">
              <strong>{{ auth.user?.username }}</strong>
              <small>{{ auth.isAdmin ? '管理员' : '个人用户' }}</small>
            </span>
          </button>
          <template #overlay>
            <a-menu @click="handleUserMenu">
              <a-menu-item key="password"><LockOutlined />修改密码</a-menu-item>
              <a-menu-divider />
              <a-menu-item key="logout" danger><LogoutOutlined />退出登录</a-menu-item>
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
  </a-layout>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  background: transparent;
}

.app-sider {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 20;
  background:
    radial-gradient(circle at 30% 0%, rgb(42 149 132 / 24%), transparent 18rem),
    #071d1b;
  box-shadow: 12px 0 40px rgb(7 24 23 / 12%);
}

.sider-brand {
  display: flex;
  align-items: center;
  height: 86px;
  padding: 0 20px;
}

.nav-menu {
  padding: 10px 12px;
  background: transparent;
  border: 0;
}

.nav-menu :deep(.ant-menu-item) {
  height: 48px;
  margin: 5px 0;
  border-radius: 11px;
  color: rgb(227 243 238 / 70%);
}

.nav-menu :deep(.ant-menu-item-selected) {
  color: white;
  background: rgb(35 157 136 / 22%);
  box-shadow: inset 3px 0 #d5a23f;
}

.sider-note {
  position: absolute;
  right: 18px;
  bottom: 24px;
  left: 18px;
  padding: 16px;
  border: 1px solid rgb(213 162 63 / 22%);
  border-radius: 14px;
  color: white;
  background: rgb(255 255 255 / 5%);
}

.sider-note span {
  display: block;
  margin-bottom: 6px;
  color: #d9b96d;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.sider-note strong {
  font-size: 13px;
}

.sider-note p {
  margin: 8px 0 0;
  color: rgb(226 242 237 / 55%);
  font-size: 11px;
  line-height: 1.6;
}

.main-layout {
  min-width: 0;
  margin-left: 244px;
  background: transparent;
  transition: margin-left 0.2s;
}

.ant-layout-sider-collapsed + .main-layout {
  margin-left: 76px;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 12;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 72px;
  padding: 0 30px;
  border-bottom: 1px solid rgb(213 224 217 / 85%);
  background: rgb(248 250 247 / 88%);
  backdrop-filter: blur(18px);
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
  background: #edf3ef;
}

.user-avatar {
  flex: 0 0 auto;
  color: white;
  background: linear-gradient(145deg, #0f766e, #164e48);
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
  min-height: calc(100vh - 72px);
  padding: 30px;
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
  .user-copy {
    display: none;
  }

  .header-eyebrow {
    display: none;
  }
}
</style>
