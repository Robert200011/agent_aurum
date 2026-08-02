import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FinanceEvidencePanel from '@/components/chat/FinanceEvidencePanel.vue'

describe('FinanceEvidencePanel', () => {
  it('separates finance facts, calculation basis and risk notice', () => {
    const wrapper = mount(FinanceEvidencePanel, {
      props: {
        dataAsOf: '2026-08-02T08:00:00+00:00',
        riskNotice: '市场价格会波动，投资可能产生损失。',
        evidence: [
          {
            evidence_id: 'evidence-1',
            tool_call_id: 'tool-call-1',
            rank: 1,
            tool_name: 'get_finance_summary',
            label: '财务摘要',
            data_as_of: '2026-08-02T08:00:00+00:00',
            period_start: '2026-08-01',
            period_end: '2026-08-02',
            currencies: ['CNY'],
            calculation_basis: '按请求区间和原币种确定性汇总。',
            facts: [
              {
                label: '支出',
                value: '120.0000',
                currency: 'CNY',
                context: null,
              },
            ],
            warning_codes: ['exchange_rate_stale'],
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('个人财务数据')
    expect(wrapper.text()).toContain('支出：120.0000 CNY')
    expect(wrapper.text()).toContain('口径：按请求区间和原币种确定性汇总。')
    expect(wrapper.text()).not.toContain('知识库依据')
    expect(wrapper.text()).toContain('风险提示')
    expect(wrapper.text()).toContain('市场价格会波动')
  })
})
