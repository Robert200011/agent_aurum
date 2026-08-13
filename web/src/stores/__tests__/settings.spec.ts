import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { settingsApi } from '@/services/settings'
import { useSettingsStore } from '@/stores/settings'

vi.mock('@/services/settings', () => ({
  settingsApi: {
    profile: vi.fn(),
    preferences: vi.fn(),
    updateProfile: vi.fn(),
    updatePreferences: vi.fn(),
  },
}))

const profile = {
  display_name: '理财用户',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-08-12T00:00:00Z',
}

const preferences = {
  default_account_id: "account-id",
  base_currency: 'USD',
  timezone: 'America/New_York',
  font_size: 'large' as const,
  layout_density: 'compact' as const,
  hide_sensitive_amounts: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-08-12T00:00:00Z',
}

describe('settings store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    document.documentElement.removeAttribute('data-font-size')
    document.documentElement.removeAttribute('data-layout-density')
    document.documentElement.removeAttribute('data-hide-sensitive-amounts')
  })

  it('loads server preferences and applies them to the document root', async () => {
    vi.mocked(settingsApi.profile).mockResolvedValue(profile)
    vi.mocked(settingsApi.preferences).mockResolvedValue(preferences)

    const store = useSettingsStore()
    await store.initialize()

    expect(store.displayName).toBe('理财用户')
    expect(store.preferences.base_currency).toBe('USD')
    expect(document.documentElement.dataset.fontSize).toBe('large')
    expect(document.documentElement.dataset.layoutDensity).toBe('compact')
    expect(document.documentElement.dataset.hideSensitiveAmounts).toBe('true')
  })

  it('applies updated appearance preferences immediately', async () => {
    vi.mocked(settingsApi.updatePreferences).mockResolvedValue(preferences)

    const store = useSettingsStore()
    await store.updatePreferences({ font_size: 'large' })

    expect(document.documentElement.dataset.fontSize).toBe('large')
    expect(document.documentElement.dataset.hideSensitiveAmounts).toBe('true')
  })

  it('restores safe defaults when the authenticated session is cleared', () => {
    const store = useSettingsStore()
    store.preferences = preferences

    store.reset()

    expect(store.preferences.base_currency).toBe('CNY')
    expect(document.documentElement.dataset.fontSize).toBe('medium')
    expect(document.documentElement.dataset.hideSensitiveAmounts).toBe('false')
  })
})
