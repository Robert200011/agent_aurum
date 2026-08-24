import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AnswerContent from '@/components/chat/AnswerContent.vue'

describe('AnswerContent', () => {
  it('renders structured plain-text formatting', () => {
    const wrapper = mount(AnswerContent, {
      props: {
        answer: '## 结论\n- 保留 **应急金** 与 `CNY`。',
      },
    })

    expect(wrapper.get('h3').text()).toBe('结论')
    expect(wrapper.get('strong').text()).toBe('应急金')
    expect(wrapper.get('code').text()).toBe('CNY')
  })

  it('renders model output as escaped text', () => {
    const wrapper = mount(AnswerContent, {
      props: {
        answer: '<img src=x onerror=alert(1)>',
      },
    })

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
  })
})
