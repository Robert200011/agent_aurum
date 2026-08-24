import { describe, expect, it } from 'vitest'

import { parseAnswerLines, parseAnswerSegments } from '@/utils/chat'

describe('chat answer rendering helpers', () => {
  it('parses safe block-level markdown without producing HTML', () => {
    expect(
      parseAnswerLines(
        '# 结论\n\n- 第一项 [1]\n2. 第二项\n普通 **文本**',
      ),
    ).toEqual([
      { kind: 'heading', level: 1, prefix: null, text: '结论' },
      { kind: 'unordered', level: 0, prefix: '•', text: '第一项 [1]' },
      { kind: 'ordered', level: 0, prefix: '2.', text: '第二项' },
      {
        kind: 'paragraph',
        level: 0,
        prefix: null,
        text: '普通 **文本**',
      },
    ])
  })

  it('recognizes emphasis and inline code as typed segments', () => {
    expect(parseAnswerSegments('参见 [2] 的 **规则** 与 `limit`。')).toEqual([
      { kind: 'text', text: '参见 [2] 的 ' },
      { kind: 'strong', text: '规则' },
      { kind: 'text', text: ' 与 ' },
      { kind: 'code', text: 'limit' },
      { kind: 'text', text: '。' },
    ])
  })
})
