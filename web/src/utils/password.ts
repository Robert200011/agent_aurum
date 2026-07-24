export const PASSWORD_MIN_LENGTH = 10
export const PASSWORD_MAX_LENGTH = 128
export const PASSWORD_COMPLEXITY_PATTERN = /^(?=[\s\S]*[A-Za-z])(?=[\s\S]*[0-9])[\s\S]+$/
export const PASSWORD_REQUIREMENT = '10–128 位，且至少包含一个英文字母和一个数字'

export function createPasswordRules(requiredMessage: string) {
  return [
    { required: true, message: requiredMessage },
    {
      min: PASSWORD_MIN_LENGTH,
      message: `密码长度不能少于 ${PASSWORD_MIN_LENGTH} 个字符`,
    },
    {
      max: PASSWORD_MAX_LENGTH,
      message: `密码长度不能超过 ${PASSWORD_MAX_LENGTH} 个字符`,
    },
    {
      pattern: PASSWORD_COMPLEXITY_PATTERN,
      message: '密码必须同时包含至少一个英文字母和一个数字',
    },
  ]
}
