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

export function defaultAccountForTransaction(
  accounts: readonly Account[],
  defaultAccountId: string | null,
): Account | undefined {
  const activeAccounts = accounts.filter((account) => account.is_active)
  return (
    activeAccounts.find((account) => account.id === defaultAccountId) ?? activeAccounts[0]
  )
}
