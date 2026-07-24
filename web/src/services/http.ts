import axios, {
  AxiosError,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

import { tokenStorage } from '@/services/token-storage'
import type { ApiErrorPayload, AuthTokenResponse } from '@/types/api'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const http = axios.create({
  baseURL,
  timeout: 20_000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

interface RetryableRequest extends InternalAxiosRequestConfig {
  _retry?: boolean
}

let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const stored = tokenStorage.get()
  if (!stored || stored.refreshExpiresAt <= Date.now()) {
    throw new Error('refresh token unavailable')
  }

  const response = await axios.post<AuthTokenResponse>(
    `${baseURL}/auth/refresh`,
    undefined,
    { timeout: 20_000, withCredentials: true },
  )
  return tokenStorage.save(response.data).accessToken
}

http.interceptors.request.use((config) => {
  const accessToken = tokenStorage.get()?.accessToken
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorPayload>) => {
    const request = error.config as RetryableRequest | undefined
    const cannotRefresh =
      request?.url?.includes('/auth/login') ||
      request?.url?.includes('/auth/register') ||
      request?.url?.includes('/auth/refresh')
    if (error.response?.status !== 401 || !request || request._retry || cannotRefresh) {
      return Promise.reject(error)
    }

    request._retry = true
    refreshPromise ??= refreshAccessToken().finally(() => {
      refreshPromise = null
    })

    try {
      const accessToken = await refreshPromise
      request.headers.Authorization = `Bearer ${accessToken}`
      return await http.request(request)
    } catch (refreshError) {
      tokenStorage.clear()
      if (window.location.pathname !== '/login') {
        window.location.assign('/login?expired=1')
      }
      return Promise.reject(refreshError)
    }
  },
)

export function apiErrorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  if (!axios.isAxiosError<ApiErrorPayload>(error)) return fallback
  const payload = error.response?.data
  if (payload?.error?.message) return payload.error.message
  if (typeof payload?.detail === 'string') return payload.detail
  if (error.code === 'ECONNABORTED') return '请求超时，请检查后端服务'
  if (!error.response) return '无法连接后端服务，请确认 Docker 和 API 已启动'
  return fallback
}

export async function requestData<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await http.request<T>(config)
  return response.data
}
