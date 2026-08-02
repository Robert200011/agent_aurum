import { expect, test } from '@playwright/test'

interface SeedResult {
  accountId: string
  incomeStatus: number
  expenseStatus: number
}

test('真实财务 Agent 与混合回答浏览器冒烟', async ({ page }) => {
  const unique = `${Date.now()}${Math.floor(Math.random() * 10_000)}`
  const username = `p56e2e${unique}`
  const password = `Aurum${unique}Safe`

  await page.goto('/register')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('邮箱', { exact: true }).fill(`${username}@example.com`)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByLabel('确认密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '创建并进入工作台' }).click()
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('heading', { name: /你的财务全景/ })).toBeVisible()

  const seed = await page.evaluate(async (): Promise<SeedResult> => {
    const stored = localStorage.getItem('aurum.auth.tokens')
    if (!stored) throw new Error('authenticated access token is unavailable')
    const accessToken = (JSON.parse(stored) as { accessToken: string }).accessToken
    const headers = {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    }
    const accountResponse = await fetch('/api/v1/finance/accounts', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        name: 'P5.6 验收账户',
        account_type: 'checking',
        currency: 'CNY',
        opening_balance: '1000.00',
      }),
    })
    if (!accountResponse.ok) throw new Error(`account seed failed: ${accountResponse.status}`)
    const account = (await accountResponse.json()) as { id: string }
    const today = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date())
    const createTransaction = (transactionType: 'income' | 'expense', amount: string) =>
      fetch('/api/v1/finance/transactions', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          account_id: account.id,
          transaction_type: transactionType,
          amount,
          currency: 'CNY',
          category: transactionType === 'income' ? '工资' : '餐饮',
          transaction_date: today,
          source: 'p5.6-e2e',
        }),
      })
    const [income, expense] = await Promise.all([
      createTransaction('income', '12000.12'),
      createTransaction('expense', '6300.34'),
    ])
    return {
      accountId: account.id,
      incomeStatus: income.status,
      expenseStatus: expense.status,
    }
  })
  expect(seed.accountId).toBeTruthy()
  expect(seed.incomeStatus).toBe(201)
  expect(seed.expenseStatus).toBe(201)

  await page.goto('/chat')
  await expect(page.getByRole('heading', { name: '智能问答' })).toBeVisible()
  await expect(page.getByText('暂无可问答项目')).toHaveCount(0)
  await page.getByRole('button', { name: '新建会话' }).first().click()
  const createDialog = page.getByRole('dialog', { name: '新建问答会话' })
  await expect(createDialog.locator('.ant-select-selection-item')).not.toHaveText('')
  await createDialog
    .getByPlaceholder('留空后将使用第一个问题自动命名')
    .fill('P5.6 浏览器验收')
  await createDialog.locator('.ant-btn-primary').click()
  await expect(page.getByText('P5.6 浏览器验收', { exact: true }).first()).toBeVisible()

  const composer = page.getByPlaceholder('输入问题，例如：这份制度对费用报销有哪些要求？')
  await composer.fill('我这个月收入、支出和净现金流是多少？')
  await page.getByRole('button', { name: '发送问题' }).click()
  await expect(page.locator('.finance-evidence').last()).toBeVisible({ timeout: 180_000 })
  await expect(page.getByText('get_finance_summary').last()).toBeVisible()
  await expect(page.getByText('分析建议').last()).toBeVisible()

  await composer.fill(
    '结合知识库，复述我本月收入、支出和净现金流，并说明旅行支出应使用哪个账户。只复述工具数字并引用原文，不要做新计算。',
  )
  await page.getByRole('button', { name: '发送问题' }).click()
  await expect(page.locator('.finance-evidence')).toHaveCount(2, { timeout: 180_000 })
  await expect(page.getByText('知识库依据').last()).toBeVisible()
  await expect(page.locator('.message-sources button').last()).toBeVisible()
})
