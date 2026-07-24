import { http } from '@/services/http'
import type { TokenPair, User } from '@/types/api'

export const authApi = {
  async login(identifier: string, password: string): Promise<TokenPair> {
    const response = await http.post<TokenPair>('/auth/login', { identifier, password })
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
  async logout(refreshToken: string | null): Promise<void> {
    await http.post('/auth/logout', { refresh_token: refreshToken })
  },
  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await http.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
  },
}
