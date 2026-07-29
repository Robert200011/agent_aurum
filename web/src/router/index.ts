import { createRouter, createWebHistory } from 'vue-router'

import { pinia } from '@/stores'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/auth/LoginView.vue'),
      meta: { guestOnly: true, title: '登录' },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/auth/RegisterView.vue'),
      meta: { guestOnly: true, title: '注册' },
    },
    {
      path: '/',
      component: () => import('@/layouts/AppShell.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { title: '财务总览' },
        },
        {
          path: 'accounts',
          name: 'accounts',
          component: () => import('@/views/AccountsView.vue'),
          meta: { title: '账户管理' },
        },
        {
          path: 'transactions',
          name: 'transactions',
          component: () => import('@/views/TransactionsView.vue'),
          meta: { title: '收支明细' },
        },
        {
          path: 'budgets',
          name: 'budgets',
          component: () => import('@/views/BudgetsView.vue'),
          meta: { title: '预算管理' },
        },
        {
          path: 'investments',
          name: 'investments',
          component: () => import('@/views/InvestmentsView.vue'),
          meta: { title: '投资组合' },
        },
        {
          path: 'admin/projects',
          name: 'admin-projects',
          component: () => import('@/views/admin/AdminProjectsView.vue'),
          meta: { title: 'Agent 项目', adminOnly: true },
        },
        {
          path: 'admin/knowledge-bases',
          name: 'admin-knowledge-bases',
          component: () => import('@/views/admin/AdminKnowledgeBasesView.vue'),
          meta: { title: '知识库工作台', adminOnly: true },
        },
        {
          path: 'change-password',
          name: 'change-password',
          component: () => import('@/views/auth/ChangePasswordView.vue'),
          meta: { title: '修改密码' },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
      meta: { title: '页面不存在' },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore(pinia)
  await auth.initialize()

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { name: auth.mustChangePassword ? 'change-password' : 'dashboard' }
  }
  if (
    auth.isAuthenticated &&
    auth.mustChangePassword &&
    to.name !== 'change-password' &&
    to.name !== 'not-found'
  ) {
    return { name: 'change-password' }
  }
  if (to.meta.adminOnly && !auth.isAdmin) {
    return { name: 'dashboard' }
  }

  document.title = `${String(to.meta.title ?? '工作台')} · Aurum Agent`
  return true
})

export default router
