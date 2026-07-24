import { beforeEach, describe, expect, it } from 'vitest'

import { tokenStorage } from '@/services/token-storage'

describe('令牌存储', () => {
  beforeEach(() => {
    tokenStorage.clear()
  })

  it('保存并读取访问令牌与刷新令牌', () => {
    tokenStorage.save({
      access_token: 'access',
      refresh_token: 'refresh',
      token_type: 'bearer',
      expires_in: 900,
      refresh_expires_in: 3600,
      must_change_password: false,
    })

    expect(tokenStorage.get()?.accessToken).toBe('access')
    expect(tokenStorage.get()?.refreshToken).toBe('refresh')
  })

  it('清除令牌时同步清理浏览器存储', () => {
    tokenStorage.save({
      access_token: 'access',
      refresh_token: 'refresh',
      token_type: 'bearer',
      expires_in: 900,
      refresh_expires_in: 3600,
      must_change_password: true,
    })

    tokenStorage.clear()
    expect(tokenStorage.get()).toBeNull()
    expect(localStorage.length).toBe(0)
  })
})
