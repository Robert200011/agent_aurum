import type { Account } from '@/types/api'
import { activeAccountsForCurrency } from '@/utils/finance'

function account(overrides: Partial<Account>): Account {
  return {
    id: crypto.randomUUID(),
    name: '测试账户',
    account_type: 'checking',
    currency: 'CNY',
    balance: '100.0000',
    is_active: true,
    created_at: '2026-07-24T00:00:00Z',
    updated_at: '2026-07-24T00:00:00Z',
    ...overrides,
  }
}

describe('总览账户币种筛选', () => {
  it('只返回当前币种下的有效账户', () => {
    const accounts = [
      account({ currency: 'CNY' }),
      account({ currency: 'HKD', name: '港币账户' }),
      account({ currency: 'HKD', name: '已归档港币账户', is_active: false }),
    ]

    const result = activeAccountsForCurrency(accounts, 'hkd')

    expect(result).toHaveLength(1)
    expect(result[0]?.name).toBe('港币账户')
  })

  it('当前币种没有账户时返回空列表', () => {
    const result = activeAccountsForCurrency([account({ currency: 'HKD' })], 'CNY')

    expect(result).toEqual([])
  })
})
