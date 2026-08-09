<script setup lang="ts">
import {
  ArrowRightOutlined,
  LockOutlined,
  UserOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import financialMapLogin from "@/assets/auth/financial-map-login-integrated.webp";
import BrandMark from "@/components/BrandMark.vue";
import WelcomeHero from "@/components/auth/WelcomeHero.vue";
import { apiErrorMessage } from "@/services/http";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const form = reactive({
  identifier: "",
  password: "",
});
const loginSection = ref<HTMLElement | null>(null);
const loginVisible = ref(false);
let loginObserver: IntersectionObserver | undefined;

onMounted(() => {
  if (!("IntersectionObserver" in window)) {
    loginVisible.value = true;
    return;
  }

  loginObserver = new IntersectionObserver(
    ([entry]) => {
      if (!entry?.isIntersecting) return;
      loginVisible.value = true;
      loginObserver?.disconnect();
    },
    { threshold: 0.16 },
  );
  if (loginSection.value) loginObserver.observe(loginSection.value);
});

onBeforeUnmount(() => loginObserver?.disconnect());

if (route.query.expired === "1") {
  message.warning("登录状态已过期，请重新登录");
}

async function submit(): Promise<void> {
  try {
    await auth.login(form.identifier.trim(), form.password);
    message.success(`欢迎回来，${auth.user?.username ?? ""}`);
    const redirect =
      typeof route.query.redirect === "string" ? route.query.redirect : "/";
    await router.replace(redirect);
  } catch (error) {
    message.error(apiErrorMessage(error, "用户名、邮箱或密码不正确"));
  }
}
</script>

<template>
  <main class="auth-page login-page">
    <WelcomeHero />

    <section
      id="login-access"
      ref="loginSection"
      class="login-section"
      :class="{ 'is-visible': loginVisible }"
      aria-labelledby="login-title"
    >
      <div class="login-art" aria-hidden="true">
        <img
          class="login-artwork"
          :src="financialMapLogin"
          alt=""
          width="1254"
          height="1254"
        />
      </div>

      <div class="login-form-panel">
        <div class="login-panel-brand"><BrandMark /></div>
        <div class="form-wrap login-form-wrap">
          <span class="form-kicker">WELCOME BACK</span>
          <h2 id="login-title">登录 Aurum</h2>
          <span class="form-brush-line" aria-hidden="true" />
          <p>使用用户名或邮箱，继续梳理你的财务脉络。</p>

          <a-form
            layout="vertical"
            :model="form"
            class="auth-form"
            @finish="submit"
          >
            <a-form-item
              label="用户名或邮箱"
              name="identifier"
              :rules="[{ required: true, message: '请输入用户名或邮箱' }]"
            >
              <a-input
                v-model:value="form.identifier"
                size="large"
                autocomplete="username"
                placeholder="请输入用户名或邮箱"
              >
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
                placeholder="请输入密码"
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
          <div class="security-note">你的账户数据始终保持私密与独立</div>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped src="./auth.css"></style>
