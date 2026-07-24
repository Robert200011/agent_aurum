<script setup lang="ts">
import { ArrowLeftOutlined, MailOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { reactive } from 'vue'
import { useRouter } from 'vue-router'

import BrandMark from '@/components/BrandMark.vue'
import { apiErrorMessage } from '@/services/http'
import { useAuthStore } from '@/stores/auth'
import { createPasswordRules, PASSWORD_REQUIREMENT } from '@/utils/password'

const router = useRouter()
const auth = useAuthStore()
const passwordRules = createPasswordRules('请输入密码')
const form = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

async function submit(): Promise<void> {
  if (form.password !== form.confirmPassword) {
    message.error('两次输入的密码不一致')
    return
  }
  try {
    await auth.register(form.username.trim(), form.email.trim(), form.password)
    message.success('账户创建成功')
    await router.replace('/')
  } catch (error) {
    message.error(apiErrorMessage(error, '注册失败，请检查输入信息'))
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-story register-story">
      <BrandMark inverse />
      <div class="story-copy">
        <span class="story-kicker">BUILD YOUR MONEY CLARITY</span>
        <h1>从今天开始，<br />建立财务秩序。</h1>
        <p>
          创建独立且受保护的个人空间。账户、交易、预算与持仓数据都由后端租户边界隔离。
        </p>
      </div>
      <div class="promise-card">
        <SafetyCertificateOutlined />
        <div>
          <strong>你的数据只属于你</strong>
          <span>应用过滤与数据库 RLS 双重执行租户隔离。</span>
        </div>
      </div>
    </section>

    <section class="auth-panel">
      <div class="mobile-logo"><BrandMark /></div>
      <div class="form-wrap register-form-wrap">
        <router-link class="back-link" to="/login"><ArrowLeftOutlined />返回登录</router-link>
        <span class="form-kicker">CREATE ACCOUNT</span>
        <h2>创建个人账户</h2>
        <p>完成注册后将自动登录并进入工作台。</p>

        <a-form layout="vertical" :model="form" class="auth-form" @finish="submit">
          <a-form-item
            label="用户名"
            name="username"
            :rules="[
              { required: true, message: '请输入用户名' },
              { min: 3, message: '用户名至少 3 个字符' },
              { pattern: /^[A-Za-z0-9_.-]+$/, message: '仅支持字母、数字及 _ . -' },
            ]"
          >
            <a-input v-model:value="form.username" size="large" autocomplete="username">
              <template #prefix><UserOutlined /></template>
            </a-input>
          </a-form-item>
          <a-form-item
            label="邮箱"
            name="email"
            :rules="[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '邮箱格式不正确' },
            ]"
          >
            <a-input v-model:value="form.email" size="large" autocomplete="email">
              <template #prefix><MailOutlined /></template>
            </a-input>
          </a-form-item>
          <a-form-item
            label="密码"
            name="password"
            :rules="passwordRules"
            :extra="PASSWORD_REQUIREMENT"
          >
            <a-input-password
              v-model:value="form.password"
              size="large"
              autocomplete="new-password"
            />
          </a-form-item>
          <a-form-item
            label="确认密码"
            name="confirmPassword"
            :rules="[{ required: true, message: '请再次输入密码' }]"
          >
            <a-input-password
              v-model:value="form.confirmPassword"
              size="large"
              autocomplete="new-password"
            />
          </a-form-item>
          <a-button type="primary" html-type="submit" size="large" block :loading="auth.loading">
            创建并进入工作台
          </a-button>
        </a-form>
      </div>
    </section>
  </main>
</template>

<style scoped src="./auth.css"></style>
