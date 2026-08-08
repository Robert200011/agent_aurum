import type { AuthTokenResponse } from '@/types/api'

const TOKEN_KEY = 'aurum.auth.tokens'

export interface StoredTokens {
  accessToken: string
  accessExpiresAt: number
  refreshExpiresAt: number
}

function load(): StoredTokens | null {
  try {
    const value = localStorage.getItem(TOKEN_KEY)
    if (!value) return null

    const candidate = JSON.parse(value) as Record<string, unknown>
    if (
      typeof candidate.accessToken !== 'string' ||
      typeof candidate.accessExpiresAt !== 'number' ||
      typeof candidate.refreshExpiresAt !== 'number'
    ) {
      localStorage.removeItem(TOKEN_KEY)
      return null
    }

    // 只复制允许持久化的字段，借此清除旧版本遗留的刷新令牌。
    const sanitized: StoredTokens = {
      accessToken: candidate.accessToken,
      accessExpiresAt: candidate.accessExpiresAt,
      refreshExpiresAt: candidate.refreshExpiresAt,
    }
    localStorage.setItem(TOKEN_KEY, JSON.stringify(sanitized))
    return sanitized
  } catch {
    localStorage.removeItem(TOKEN_KEY)
    return null
  }
}

let tokens = load()

export const tokenStorage = {
  get(): StoredTokens | null {
    return tokens
  },
  save(pair: AuthTokenResponse): StoredTokens {
    const now = Date.now()
    tokens = {
      accessToken: pair.access_token,
      accessExpiresAt: now + pair.expires_in * 1000,
      refreshExpiresAt: now + pair.refresh_expires_in * 1000,
    }
    localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens))
    return tokens
  },
  clear(): void {
    tokens = null
    localStorage.removeItem(TOKEN_KEY)
  },
}
