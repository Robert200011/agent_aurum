import { beforeEach, describe, expect, it, vi } from 'vitest'

import { tokenStorage } from '@/services/token-storage'

describe('令牌存储', () => {
  beforeEach(() => {
    tokenStorage.clear()
  })

  it('仅保存访问令牌和非敏感的刷新期限', () => {
    tokenStorage.save({
      access_token: 'access',
      token_type: 'bearer',
      expires_in: 900,
      refresh_expires_in: 3600,
    })

    expect(tokenStorage.get()?.accessToken).toBe('access')
    const persisted = JSON.parse(localStorage.getItem('aurum.auth.tokens') ?? '{}') as object
    expect(persisted).not.toHaveProperty('refreshToken')
  })

  it('清除令牌时同步清理浏览器存储', () => {
    tokenStorage.save({
      access_token: 'access',
      token_type: 'bearer',
      expires_in: 900,
      refresh_expires_in: 3600,
    })

    tokenStorage.clear()
    expect(tokenStorage.get()).toBeNull()
    expect(localStorage.length).toBe(0)
  })

  it('加载旧版会话时移除历史刷新令牌', async () => {
    localStorage.setItem(
      'aurum.auth.tokens',
      JSON.stringify({
        accessToken: 'access',
        refreshToken: 'legacy-refresh-secret',
        accessExpiresAt: Date.now() + 900_000,
        refreshExpiresAt: Date.now() + 3_600_000,
      }),
    )
    vi.resetModules()

    const { tokenStorage: reloadedStorage } = await import('@/services/token-storage')
    const persisted = JSON.parse(localStorage.getItem('aurum.auth.tokens') ?? '{}') as object

    expect(reloadedStorage.get()?.accessToken).toBe('access')
    expect(persisted).not.toHaveProperty('refreshToken')
  })
})
