import type { Account } from '@/types/api'

export function activeAccountsForCurrency(
  accounts: readonly Account[],
  currency: string,
): Account[] {
  const normalizedCurrency = currency.toUpperCase()
  return accounts.filter(
    (account) => account.is_active && account.currency.toUpperCase() === normalizedCurrency,
  )
}
