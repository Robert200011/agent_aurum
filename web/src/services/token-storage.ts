import type { TokenPair } from '@/types/api'

const TOKEN_KEY = 'aurum.auth.tokens'

export interface StoredTokens {
  accessToken: string
  refreshToken: string
  accessExpiresAt: number
  refreshExpiresAt: number
  mustChangePassword: boolean
}

function load(): StoredTokens | null {
  try {
    const value = localStorage.getItem(TOKEN_KEY)
    return value ? (JSON.parse(value) as StoredTokens) : null
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
  save(pair: TokenPair): StoredTokens {
    const now = Date.now()
    tokens = {
      accessToken: pair.access_token,
      refreshToken: pair.refresh_token,
      accessExpiresAt: now + pair.expires_in * 1000,
      refreshExpiresAt: now + pair.refresh_expires_in * 1000,
      mustChangePassword: pair.must_change_password,
    }
    localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens))
    return tokens
  },
  clear(): void {
    tokens = null
    localStorage.removeItem(TOKEN_KEY)
  },
  setMustChangePassword(value: boolean): void {
    if (!tokens) return
    tokens = { ...tokens, mustChangePassword: value }
    localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens))
  },
}
