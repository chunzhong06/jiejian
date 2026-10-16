// 核对显示文字不会把未知或尚未完成的观察写成“没有发生”。
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { ActionResultStory } from '../../../api/checks/currentChecks'
import { BusinessEffects } from './ResultOverview'
import { effectSentence } from './resultLanguage'
afterEach(cleanup)
it('自定义业务名称保持原文，未知文件接收不写成未收到', () => {
  expect(effectSentence('客户自定结果', 'ABSENT')).toBe('本次未发现“客户自定结果”')
  expect(effectSentence('内部完整包已被接收', 'UNKNOWN')).toBe('尚不能确认是否完整收到内部完整包')
})
it('未闭合的ABSENT仍显示无法确认，不输出本次观察已完成', () => {
  const action = { fact_comparison: { effects: [{effect_id:'e', business_label:'内部完整包已被接收', observed_state:'ABSENT', judgement:'没有观察到充分证据，不等于业务后果没有发生。'}] } } as ActionResultStory
  render(<BusinessEffects action={action}/>)
  expect(screen.getByText('尚不能确认是否完整收到内部完整包')).toBeInTheDocument()
  expect(screen.queryByText(/本次观察已完成/)).not.toBeInTheDocument()
})
