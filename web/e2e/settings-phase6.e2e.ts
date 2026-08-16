import { expect, test } from '@playwright/test'

const user = {
  id: 'phase6-user-id',
  username: 'phase6_user',
  email: 'phase6@example.com',
  status: 'active',
  password_changed_at: '2026-08-01T00:00:00Z',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-08-13T00:00:00Z',
}

const profile = {
  display_name: '阶段六用户',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-08-13T00:00:00Z',
}

const preferences = {
  default_account_id: 'phase6-account-id',
  base_currency: 'CNY',
  timezone: 'Asia/Shanghai',
  font_size: 'medium',
  layout_density: 'comfortable',
  hide_sensitive_amounts: false,
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-08-13T00:00:00Z',
}

const accountList = {
  items: [
    {
      id: 'phase6-account-id',
      name: '日常账户',
      account_type: 'checking',
      currency: 'CNY',
      balance: '1200.0000',
      is_active: true,
      created_at: '2026-01-15T00:00:00Z',
      updated_at: '2026-08-13T00:00:00Z',
    },
  ],
  page: 1,
  page_size: 200,
  total: 1,
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const now = Date.now()
    localStorage.setItem(
      'aurum.auth.tokens',
      JSON.stringify({
        accessToken: 'phase6-access-token',
        accessExpiresAt: now + 3_600_000,
        refreshExpiresAt: now + 86_400_000,
      }),
    )
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const responses: Record<string, object> = {
      '/api/v1/users/me': user,
      '/api/v1/users/me/profile': profile,
      '/api/v1/users/me/preferences': preferences,
      '/api/v1/finance/accounts': accountList,
    }
    const payload = responses[path]
    if (payload) {
      await route.fulfill({ status: 200, contentType: 'application/json', json: payload })
      return
    }
    await route.fulfill({ status: 404, contentType: 'application/json', json: {} })
  })
})

test('设置中心桌面端展开和注销二次确认', async ({ page }) => {
  await page.goto('/')
  const settingsTrigger = page.getByRole('button', { name: '打开设置中心' })
  const triggerBox = await settingsTrigger.boundingBox()
  await settingsTrigger.click()

  await expect(page.getByRole('heading', { name: '设置中心' })).toBeVisible()
  await expect(page.getByLabel('当前账户').getByText('阶段六用户')).toBeVisible()
  const menuBox = await page.locator('.settings-drawer').boundingBox()
  expect(triggerBox).not.toBeNull()
  expect(menuBox).not.toBeNull()
  expect(menuBox?.y).toBeGreaterThanOrEqual((triggerBox?.y ?? 0) + (triggerBox?.height ?? 0))
  await expect(page.locator('.ant-drawer-mask')).toHaveCount(0)

  await page.getByRole('button', { name: /财务账户/ }).click()
  const accountsPanel = page.getByRole('region', { name: /财务账户/ })
  await expect(accountsPanel).toBeVisible()
  await expect(accountsPanel.getByText('日常账户')).toBeVisible()
  await expect(accountsPanel.getByText('¥1,200.00')).toBeVisible()

  await page.getByRole('button', { name: /注销账户/ }).click()
  await page.getByRole('button', { name: '申请注销账户' }).click()
  const dialog = page.getByRole('dialog', { name: '二次确认注销账户' })
  const usernameInput = dialog.getByPlaceholder('当前用户名')
  const confirmButton = dialog.getByRole('button', { name: '确认注销' })

  await expect(dialog).toBeVisible()
  await expect(usernameInput).toBeFocused()
  await expect(confirmButton).toBeDisabled()

  await dialog.getByRole('checkbox').check()
  await usernameInput.fill(user.username)
  await dialog.getByPlaceholder('用于验证本人操作').fill('Only-for-browser-check-123')
  await expect(confirmButton).toBeEnabled()
})

test('设置中心在 320px 移动视口内保持可操作', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 })
  await page.goto('/')
  await page.getByRole('button', { name: '打开设置中心' }).click()
  await page.getByRole('button', { name: /财务账户/ }).click()

  const drawer = page.locator('.settings-drawer')
  const accountsPanel = page.getByRole('region', { name: /财务账户/ })
  const drawerBox = await drawer.boundingBox()

  expect(drawerBox).not.toBeNull()
  expect(drawerBox?.width).toBeLessThanOrEqual(320)
  await expect(accountsPanel.getByRole('button', { name: '保存默认账户' })).toBeVisible()
  await expect(accountsPanel.getByRole('button', { name: '管理全部账户' })).toBeVisible()
})

test('没有财务账户时仍可保存财务偏好和显示偏好', async ({ page }) => {
  const preferenceUpdates: Record<string, unknown>[] = []
  await page.route('**/api/v1/finance/accounts**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      json: { items: [], page: 1, page_size: 200, total: 0 },
    })
  })
  page.on('request', (request) => {
    if (
      request.method() === 'PATCH' &&
      new URL(request.url()).pathname === '/api/v1/users/me/preferences'
    ) {
      preferenceUpdates.push(request.postDataJSON() as Record<string, unknown>)
    }
  })

  await page.goto('/')
  await page.getByRole('button', { name: '打开设置中心' }).click()
  await page.getByRole('button', { name: /财务偏好/ }).click()
  await expect(page.getByRole('region', { name: /财务偏好/ })).toBeVisible()
  await page.getByRole('button', { name: '保存财务偏好' }).click()

  await page.getByRole('button', { name: /显示偏好/ }).click()
  await page.getByRole('button', { name: '保存显示偏好' }).click()

  await expect.poll(() => preferenceUpdates.length).toBe(2)
  expect(preferenceUpdates[0]).toMatchObject({
    base_currency: 'CNY',
    timezone: 'Asia/Shanghai',
  })
  expect(preferenceUpdates[1]).toMatchObject({
    font_size: 'medium',
    layout_density: 'comfortable',
    hide_sensitive_amounts: false,
  })
})
