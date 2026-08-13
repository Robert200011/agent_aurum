import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { authApi } from "@/services/auth";
import { tokenStorage } from "@/services/token-storage";
import { useSettingsStore } from "@/stores/settings";
import type { User } from "@/types/api";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const initialized = ref(false);
  const loading = ref(false);

  const isAuthenticated = computed(() =>
    Boolean(user.value && tokenStorage.get()?.accessToken),
  );

  async function initialize(): Promise<void> {
    if (initialized.value) return;
    const stored = tokenStorage.get();
    if (!stored || stored.refreshExpiresAt <= Date.now()) {
      tokenStorage.clear();
      initialized.value = true;
      return;
    }
    try {
      user.value = await authApi.me();
    } catch {
      tokenStorage.clear();
      user.value = null;
    } finally {
      initialized.value = true;
    }
  }

  async function login(identifier: string, password: string): Promise<void> {
    loading.value = true;
    try {
      tokenStorage.save(await authApi.login(identifier, password));
      user.value = await authApi.me();
      initialized.value = true;
    } finally {
      loading.value = false;
    }
  }

  async function register(
    username: string,
    email: string,
    password: string,
  ): Promise<void> {
    loading.value = true;
    try {
      await authApi.register(username, email, password);
      tokenStorage.save(await authApi.login(username, password));
      user.value = await authApi.me();
      initialized.value = true;
    } finally {
      loading.value = false;
    }
  }

  async function logout(): Promise<void> {
    const accessToken = tokenStorage.get()?.accessToken;
    tokenStorage.clear();
    user.value = null;
    initialized.value = true;
    useSettingsStore().reset();

    if (!accessToken) return;

    try {
      await authApi.logout(accessToken);
    } catch {
      // 本地会话已经失效，服务端不可用不应阻止用户退出。
    }
  }

  async function changePassword(
    currentPassword: string,
    newPassword: string,
  ): Promise<void> {
    await authApi.changePassword(currentPassword, newPassword);
    tokenStorage.clear();
    user.value = null;
    initialized.value = true;
    useSettingsStore().reset();
  }

  async function deactivateAccount(
    username: string,
    currentPassword: string,
  ): Promise<void> {
    await authApi.deactivateAccount(username, currentPassword);
    tokenStorage.clear();
    user.value = null;
    initialized.value = true;
    useSettingsStore().reset();
  }

  return {
    user,
    initialized,
    loading,
    isAuthenticated,
    initialize,
    login,
    register,
    logout,
    changePassword,
    deactivateAccount,
  };
});
