import { describe, expect, it } from 'vitest'

import {
  citationLocation,
  parseAnswerLines,
  parseAnswerSegments,
} from '@/utils/chat'

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

  it('recognizes citations, emphasis and inline code as typed segments', () => {
    expect(parseAnswerSegments('参见 [2] 的 **规则** 与 `limit`。')).toEqual([
      { kind: 'text', text: '参见 ', citationId: null },
      { kind: 'citation', text: '[2]', citationId: 2 },
      { kind: 'text', text: ' 的 ', citationId: null },
      { kind: 'strong', text: '规则', citationId: null },
      { kind: 'text', text: ' 与 ', citationId: null },
      { kind: 'code', text: 'limit', citationId: null },
      { kind: 'text', text: '。', citationId: null },
    ])
  })

  it('builds a readable location from document coordinates', () => {
    expect(
      citationLocation({
        page: 3,
        section: '费用报销',
        sheet_name: null,
        row_start: 10,
        row_end: 12,
      }),
    ).toBe('第 3 页 · 费用报销 · 第 10–12 行')
  })
})
