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
  async logout(): Promise<void> {
    await http.post('/auth/logout')
  },
  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await http.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
  },
}
