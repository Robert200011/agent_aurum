import { http } from '@/services/http'
import type { AuthTokenResponse, User } from '@/types/api'

export const authApi = {
  async login(identifier: string, password: string): Promise<AuthTokenResponse> {
    const response = await http.post<AuthTokenResponse>('/auth/login', { identifier, password })
    return response.data
  },
  async register(username: string, email: string, password: string): Promise<User> {
    const response = await http.post<User>('/auth/register', { username, email, password })
    return response.data
  },
  async me(): Promise<User> {
    const response = await http.get<User>('/users/me')
    return response.data
  },
  async logout(accessToken: string): Promise<void> {
    await http.post('/auth/logout', undefined, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  },
  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await http.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
  },
  async deactivateAccount(username: string, currentPassword: string): Promise<void> {
    await http.post('/auth/deactivate-account', {
      username,
      current_password: currentPassword,
      confirmation: 'DEACTIVATE',
    })
  },
}
