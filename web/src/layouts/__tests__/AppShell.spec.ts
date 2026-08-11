import { shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AppShell from '@/layouts/AppShell.vue'

const replace = vi.fn()
const logout = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/', meta: { title: '财务总览' } }),
  useRouter: () => ({ push: vi.fn(), replace }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { username: 'user_test' },
    logout,
  }),
}))

describe('AppShell logout confirmation', () => {
  beforeEach(() => {
    replace.mockReset()
    logout.mockReset()
    logout.mockResolvedValue(undefined)
  })

  it('waits for confirmation before logging out', async () => {
    const wrapper = shallowMount(AppShell, {
      global: {
        stubs: {
          RouterView: {
            template: '<div><slot :Component="null" /></div>',
          },
        },
      },
    })
    const setup = (
      wrapper.vm.$ as unknown as {
        setupState: {
          handleUserMenu: (event: { key: string }) => Promise<void>
          confirmLogout: () => Promise<void>
          logoutConfirmOpen: boolean
        }
      }
    ).setupState

    await setup.handleUserMenu({ key: 'logout' })

    expect(setup.logoutConfirmOpen).toBe(true)
    expect(logout).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()

    await setup.confirmLogout()

    expect(logout).toHaveBeenCalledOnce()
    expect(replace).toHaveBeenCalledWith('/login')
  })

  it('opens and closes the embedded agent from the sidebar button', async () => {
    const wrapper = shallowMount(AppShell, {
      global: {
        stubs: {
          RouterView: {
            template: '<div><slot :Component="null" /></div>',
          },
          ChatView: true,
        },
      },
    })
    const launcher = wrapper.get('.assistant-entry')

    expect(launcher.attributes('aria-expanded')).toBe('false')

    await launcher.trigger('click')

    expect(launcher.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.agent-drawer').isVisible()).toBe(true)

    await wrapper.get('.agent-drawer-header button').trigger('click')

    expect(launcher.attributes('aria-expanded')).toBe('false')
  })
})
