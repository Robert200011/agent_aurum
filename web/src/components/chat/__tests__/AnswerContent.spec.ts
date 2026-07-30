import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AnswerContent from '@/components/chat/AnswerContent.vue'

describe('AnswerContent', () => {
  it('emits only available citation markers', async () => {
    const wrapper = mount(AnswerContent, {
      props: {
        answer: '结论见 [1]，无效标记 [9]。',
        citationIds: [1],
      },
    })

    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(1)
    await buttons[0]?.trigger('click')
    expect(wrapper.emitted('citation')).toEqual([[1]])
    expect(wrapper.text()).toContain('[9]')
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
