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
})
