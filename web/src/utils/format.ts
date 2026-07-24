import dayjs from 'dayjs'

import type { MoneyValue } from '@/types/api'

export const accountTypeLabels = {
  cash: '现金账户',
  checking: '活期账户',
  savings: '储蓄账户',
  credit: '信用账户',
  investment: '投资账户',
  other: '其他账户',
} as const

export const assetTypeLabels = {
  stock: '股票',
  fund: '基金',
  etf: 'ETF',
  bond: '债券',
  deposit: '存款',
  crypto: '数字资产',
  other: '其他',
} as const

export const budgetPeriodLabels = {
  monthly: '月度',
  quarterly: '季度',
  yearly: '年度',
  custom: '自定义',
} as const

export function toNumber(value: MoneyValue | null | undefined): number {
  if (value === null || value === undefined) return 0
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export function formatMoney(
  value: MoneyValue | null | undefined,
  currency = 'CNY',
  empty = '—',
): string {
  if (value === null || value === undefined) return empty
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(toNumber(value))
}

export function formatNumber(value: MoneyValue | null | undefined, digits = 4): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: digits,
  }).format(toNumber(value))
}

export function formatDate(value: string | null | undefined, pattern = 'YYYY-MM-DD'): string {
  return value ? dayjs(value).format(pattern) : '—'
}

export function currentMonthRange(): [string, string] {
  const now = dayjs()
  return [now.startOf('month').format('YYYY-MM-DD'), now.endOf('month').format('YYYY-MM-DD')]
}
