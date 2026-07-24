import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { authApi } from '@/services/auth'
import { tokenStorage } from '@/services/token-storage'
import type { User } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const initialized = ref(false)
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(user.value && tokenStorage.get()?.accessToken))
  const isAdmin = computed(() => user.value?.role === 'admin')
  const mustChangePassword = computed(
    () => user.value?.must_change_password ?? tokenStorage.get()?.mustChangePassword ?? false,
  )

  async function initialize(): Promise<void> {
    if (initialized.value) return
    const stored = tokenStorage.get()
    if (!stored || stored.refreshExpiresAt <= Date.now()) {
      tokenStorage.clear()
      initialized.value = true
      return
    }
    try {
      user.value = await authApi.me()
    } catch {
      tokenStorage.clear()
      user.value = null
    } finally {
      initialized.value = true
    }
  }

  async function login(identifier: string, password: string): Promise<void> {
    loading.value = true
    try {
      tokenStorage.save(await authApi.login(identifier, password))
      user.value = await authApi.me()
      initialized.value = true
    } finally {
      loading.value = false
    }
  }

  async function register(username: string, email: string, password: string): Promise<void> {
    loading.value = true
    try {
      await authApi.register(username, email, password)
      tokenStorage.save(await authApi.login(username, password))
      user.value = await authApi.me()
      initialized.value = true
    } finally {
      loading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      if (tokenStorage.get()?.accessToken) await authApi.logout()
    } finally {
      tokenStorage.clear()
      user.value = null
      initialized.value = true
    }
  }

  async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await authApi.changePassword(currentPassword, newPassword)
    tokenStorage.clear()
    user.value = null
    initialized.value = true
  }

  return {
    user,
    initialized,
    loading,
    isAuthenticated,
    isAdmin,
    mustChangePassword,
    initialize,
    login,
    register,
    logout,
    changePassword,
  }
})
