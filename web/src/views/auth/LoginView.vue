<script setup lang="ts">
import { ArrowRightOutlined, LockOutlined, UserOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import BrandMark from '@/components/BrandMark.vue'
import { apiErrorMessage } from '@/services/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const form = reactive({
  identifier: '',
  password: '',
})

if (route.query.expired === '1') {
  message.warning('登录状态已过期，请重新登录')
}

async function submit(): Promise<void> {
  try {
    await auth.login(form.identifier.trim(), form.password)
    message.success(`欢迎回来，${auth.user?.username ?? ''}`)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (error) {
    message.error(apiErrorMessage(error, '用户名、邮箱或密码不正确'))
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-story">
      <BrandMark inverse />
      <div class="story-copy">
        <span class="story-kicker">YOUR FINANCIAL OPERATING SYSTEM</span>
        <h1>让每一笔资金<br />都有清晰去向。</h1>
        <p>
          在一个可信赖的工作台中管理现金流、预算与投资。
          所有核心财务结果均来自确定性计算，而非模型猜测。
        </p>
      </div>
      <div class="story-metrics">
        <div><strong>01</strong><span>账本级数据隔离</span></div>
        <div><strong>02</strong><span>固定精度财务计算</span></div>
        <div><strong>03</strong><span>可追溯审计记录</span></div>
      </div>
    </section>

    <section class="auth-panel">
      <div class="mobile-logo"><BrandMark /></div>
      <div class="form-wrap">
        <span class="form-kicker">SECURE ACCESS</span>
        <h2>登录 Aurum</h2>
        <p>使用用户名或邮箱继续进入你的财务工作台。</p>

        <a-form layout="vertical" :model="form" class="auth-form" @finish="submit">
          <a-form-item
            label="用户名或邮箱"
            name="identifier"
            :rules="[{ required: true, message: '请输入用户名或邮箱' }]"
          >
            <a-input v-model:value="form.identifier" size="large" autocomplete="username">
              <template #prefix><UserOutlined /></template>
            </a-input>
          </a-form-item>
          <a-form-item
            label="密码"
            name="password"
            :rules="[{ required: true, message: '请输入密码' }]"
          >
            <a-input-password
              v-model:value="form.password"
              size="large"
              autocomplete="current-password"
            >
              <template #prefix><LockOutlined /></template>
            </a-input-password>
          </a-form-item>
          <a-button
            type="primary"
            html-type="submit"
            size="large"
            block
            :loading="auth.loading"
            class="submit-button"
          >
            进入工作台
            <ArrowRightOutlined />
          </a-button>
        </a-form>

        <div class="auth-switch">
          还没有账户？
          <router-link to="/register">立即注册</router-link>
        </div>
        <div class="security-note">短期访问令牌 · 自动安全续期 · 退出即撤销</div>
      </div>
    </section>
  </main>
</template>

<style scoped src="./auth.css"></style>
