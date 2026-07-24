<script setup lang="ts">
import { LockOutlined, SafetyCertificateOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { apiErrorMessage } from '@/services/http'
import { useAuthStore } from '@/stores/auth'
import { createPasswordRules, PASSWORD_REQUIREMENT } from '@/utils/password'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const newPasswordRules = createPasswordRules('请输入新密码')
const form = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
})

async function submit(): Promise<void> {
  if (form.newPassword !== form.confirmPassword) {
    message.error('两次输入的新密码不一致')
    return
  }
  loading.value = true
  try {
    await auth.changePassword(form.currentPassword, form.newPassword)
    message.success('密码已更新，请重新登录')
    await router.replace('/login')
  } catch (error) {
    message.error(apiErrorMessage(error, '密码修改失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page-shell password-page">
    <div class="page-heading">
      <div>
        <h1>修改密码</h1>
        <p>
          更新密码后，当前访问令牌和所有刷新令牌都会被撤销，你需要重新登录。
        </p>
      </div>
    </div>

    <a-alert
      v-if="auth.mustChangePassword"
      type="warning"
      show-icon
      message="首次登录必须修改初始密码"
      description="完成修改前，其他财务功能暂不可访问。"
    />

    <a-card class="surface-card password-card" :bordered="false">
      <div class="security-heading">
        <div class="security-icon"><SafetyCertificateOutlined /></div>
        <div>
          <strong>账户安全验证</strong>
          <span>请输入当前密码，并设置符合安全规则的新密码。</span>
        </div>
      </div>
      <a-form layout="vertical" :model="form" @finish="submit">
        <a-form-item
          label="当前密码"
          name="currentPassword"
          :rules="[{ required: true, message: '请输入当前密码' }]"
        >
          <a-input-password v-model:value="form.currentPassword" size="large">
            <template #prefix><LockOutlined /></template>
          </a-input-password>
        </a-form-item>
        <a-form-item
          label="新密码"
          name="newPassword"
          :rules="newPasswordRules"
          :extra="PASSWORD_REQUIREMENT"
        >
          <a-input-password v-model:value="form.newPassword" size="large" />
        </a-form-item>
        <a-form-item
          label="确认新密码"
          name="confirmPassword"
          :rules="[{ required: true, message: '请确认新密码' }]"
        >
          <a-input-password v-model:value="form.confirmPassword" size="large" />
        </a-form-item>
        <a-button type="primary" html-type="submit" size="large" block :loading="loading">
          更新密码并重新登录
        </a-button>
      </a-form>
    </a-card>
  </div>
</template>

<style scoped>
.password-page {
  max-width: 700px;
  margin: 0 auto;
}

.password-card {
  padding: 10px;
}

.security-heading {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 26px;
}

.security-icon {
  display: grid;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  color: var(--mint-700);
  background: var(--mint-100);
  font-size: 22px;
  place-items: center;
}

.security-heading > div:last-child {
  display: grid;
  gap: 4px;
}

.security-heading span {
  color: var(--ink-500);
  font-size: 13px;
}
</style>
