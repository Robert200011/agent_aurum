import { describe, expect, it } from 'vitest'

import { currentMonthRange, formatMoney, toNumber } from '@/utils/format'

describe('财务格式化工具', () => {
  it('同时支持后端返回的字符串与数字金额', () => {
    expect(toNumber('123.4500')).toBe(123.45)
    expect(toNumber(88)).toBe(88)
    expect(toNumber(null)).toBe(0)
  })

  it('缺失估值不会被展示为零', () => {
    expect(formatMoney(null, 'CNY')).toBe('—')
  })

  it('生成包含边界的当月日期范围', () => {
    const [start, end] = currentMonthRange()
    expect(start).toMatch(/^\d{4}-\d{2}-01$/)
    expect(end >= start).toBe(true)
  })
})
