import axios, {
  AxiosError,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

import { tokenStorage } from '@/services/token-storage'
import type { ApiErrorPayload, AuthTokenResponse } from '@/types/api'

export const apiBaseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const http = axios.create({
  baseURL: apiBaseURL,
  timeout: 20_000,
  withCredentials: true,
})

interface RetryableRequest extends InternalAxiosRequestConfig {
  _retry?: boolean
}

let refreshPromise: Promise<string> | null = null

function validationDetailMessage(detail: unknown): string | null {
  if (typeof detail !== 'object' || detail === null) return null

  const record = detail as Record<string, unknown>
  const message = typeof record.msg === 'string' ? record.msg : null
  if (!message) return null

  const location = Array.isArray(record.loc)
    ? record.loc
        .filter((part) => part !== 'body')
        .filter(
          (part): part is string | number =>
            typeof part === 'string' || typeof part === 'number',
        )
        .join('.')
    : ''

  return location ? `${location}：${message}` : message
}

async function refreshAccessToken(): Promise<string> {
  const stored = tokenStorage.get()
  if (!stored || stored.refreshExpiresAt <= Date.now()) {
    throw new Error('refresh token unavailable')
  }

  const response = await axios.post<AuthTokenResponse>(
    apiURL('/auth/refresh'),
    undefined,
    { timeout: 20_000, withCredentials: true },
  )
  return tokenStorage.save(response.data).accessToken
}

function apiURL(path: string): string {
  return `${apiBaseURL.replace(/\/$/, '')}/${path.replace(/^\//, '')}`
}

export async function authorizedFetch(
  path: string,
  init: RequestInit,
): Promise<Response> {
  const execute = (): Promise<Response> => {
    const headers = new Headers(init.headers)
    const accessToken = tokenStorage.get()?.accessToken
    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
    return fetch(apiURL(path), {
      ...init,
      headers,
      credentials: 'include',
    })
  }

  let response = await execute()
  if (response.status !== 401) return response

  try {
    refreshPromise ??= refreshAccessToken().finally(() => {
      refreshPromise = null
    })
    await refreshPromise
    response = await execute()
    return response
  } catch (error) {
    tokenStorage.clear()
    if (window.location.pathname !== '/login') {
      window.location.assign('/login?expired=1')
    }
    throw error
  }
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
      request?.url?.includes('/auth/refresh') ||
      request?.url?.includes('/auth/logout')
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
  if (payload?.error?.code === 'validation_error' && Array.isArray(payload.details)) {
    const details = payload.details
      .map(validationDetailMessage)
      .filter((detail): detail is string => detail !== null)
    if (details.length) return `请求参数校验失败：${details.join('；')}`
  }
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
