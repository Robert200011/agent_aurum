import {
  createPasswordRules,
  PASSWORD_COMPLEXITY_PATTERN,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
} from '@/utils/password'

describe('密码策略', () => {
  it('与后端默认长度和复杂度规则一致', () => {
    expect(PASSWORD_MIN_LENGTH).toBe(10)
    expect(PASSWORD_MAX_LENGTH).toBe(128)
    expect(PASSWORD_COMPLEXITY_PATTERN.test('Aurum2026test')).toBe(true)
    expect(PASSWORD_COMPLEXITY_PATTERN.test('123456789012')).toBe(false)
    expect(PASSWORD_COMPLEXITY_PATTERN.test('onlyletters')).toBe(false)
  })

  it('生成完整的表单校验规则', () => {
    const rules = createPasswordRules('请输入密码')

    expect(rules).toHaveLength(4)
    expect(rules[0]).toMatchObject({ required: true, message: '请输入密码' })
    expect(rules[1]).toMatchObject({ min: 10 })
    expect(rules[2]).toMatchObject({ max: 128 })
    expect(rules[3]).toMatchObject({ pattern: PASSWORD_COMPLEXITY_PATTERN })
  })
})
