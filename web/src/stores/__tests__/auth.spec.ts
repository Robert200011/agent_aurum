import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authApi } from '@/services/auth'
import { tokenStorage } from '@/services/token-storage'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/services/auth', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    me: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
    deactivateAccount: vi.fn(),
  },
}))

describe('auth store logout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    tokenStorage.clear()
    vi.clearAllMocks()
  })

  it('immediately clears local authentication before the server responds', async () => {
    let resolveLogout: (() => void) | undefined
    vi.mocked(authApi.logout).mockReturnValue(
      new Promise<void>((resolve) => {
        resolveLogout = resolve
      }),
    )
    tokenStorage.save({
      access_token: 'access-token',
      token_type: 'bearer',
      expires_in: 900,
      refresh_expires_in: 3600,
    })

    const pending = useAuthStore().logout()

    expect(tokenStorage.get()).toBeNull()
    expect(authApi.logout).toHaveBeenCalledWith('access-token')

    resolveLogout?.()
    await pending
  })

  it('keeps the user logged out when the server request fails', async () => {
    vi.mocked(authApi.logout).mockRejectedValue(new Error('network unavailable'))
    tokenStorage.save({
      access_token: 'access-token',
      token_type: 'bearer',
      expires_in: 900,
      refresh_expires_in: 3600,
    })

    await expect(useAuthStore().logout()).resolves.toBeUndefined()
    expect(tokenStorage.get()).toBeNull()
  })

  it('clears local identity only after account deactivation succeeds', async () => {
    vi.mocked(authApi.deactivateAccount).mockResolvedValue(undefined)
    tokenStorage.save({
      access_token: 'access-token',
      token_type: 'bearer',
      expires_in: 900,
      refresh_expires_in: 3600,
    })
    const store = useAuthStore()
    store.user = {
      id: 'user-id',
      username: 'aurum_user',
      email: 'user@example.com',
      status: 'active',
      password_changed_at: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }

    await store.deactivateAccount('aurum_user', 'Correct-pass-123')

    expect(authApi.deactivateAccount).toHaveBeenCalledWith(
      'aurum_user',
      'Correct-pass-123',
    )
    expect(tokenStorage.get()).toBeNull()
    expect(store.user).toBeNull()
  })
})
