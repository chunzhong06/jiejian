// 分类展示未知原因，确保过程记录不被翻译成业务结果已确认。
import { expect, it } from 'vitest'
import { observationStatus } from './observationPresentation'
import { observation } from '../../../testing/fixtures/results'
it('不适用阶段不是读取失败，单点状态不是业务效果缺失', () => {
  expect(observationStatus({ ...observation, state:'UNKNOWN', reason_codes:['OBSERVER_PHASE_UNAVAILABLE'] }).label).toBe('本阶段不采集')
  expect(observationStatus({ ...observation, phase:'BASELINE', state:'UNKNOWN', reason_codes:['OBSERVATION_UNINTERPRETED'] }).label).toBe('初始对照记录')
  expect(observationStatus({ ...observation, phase:'RECOVERY', state:'UNKNOWN', reason_codes:['OBSERVATION_UNINTERPRETED'] }).label).toBe('恢复对照记录')
})
it('过程记录只能说明来源已采集，不能提升成最终证明', () => {
  const value = { ...observation, level:'DIAGNOSIS_REQUIRED' as const, state:'UNKNOWN' as const, reason_codes:['SOURCE_RECORDS_AVAILABLE','REQUIRED_OBSERVER_INCOMPLETE'] }
  expect(observationStatus(value).label).toBe('已取得关联过程记录')
  expect(observationStatus({ ...value, level:'VERDICT_REQUIRED' }).label).toBe('观察依据不完整')
})
it('消息读取上限、投影能力缺口和未闭合缺失分别说明', () => {
  expect(observationStatus({ ...observation, state:'UNKNOWN', reason_codes:['AZURE_QUEUE_MESSAGE_LIMIT'] }).label).toBe('消息读取达到上限')
  expect(observationStatus({ ...observation, state:'UNKNOWN', reason_codes:['EFFECT_PROJECTOR_UNSUPPORTED'] }).label).toBe('不能用于判断该业务后果')
  expect(observationStatus({ ...observation, state:'ABSENT', closure:'OPEN' }).label).toBe('暂未观察到')
})
it('旧响应缺少结构化说明时，不将不可靠的确认状态展示成业务事实', () => {
  expect(observationStatus({ ...observation, state:'CONFIRMED', reliable:false }).label).toBe('观察依据不完整')
})
