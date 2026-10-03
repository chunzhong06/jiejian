// 同源阶段聚合不跨证明串联，阶段缺口和证据引用始终可见。
import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { EvidenceExplanation, ObservationReading } from '../../../api/checks/currentChecks'
import { ObservationSources } from './ObservationSources'
import { observationGroups } from './observationPresentation'
import { source } from '../../../testing/fixtures/results'

const process: ObservationReading = { kind:'PROCESS',label:'已取得关联过程记录',detail:'仅用于追踪本次操作，不能单独证明交付包生成。',attention:false }
const failure: ObservationReading = { kind:'UNAVAILABLE',label:'来源读取超时',detail:'未取得完整来源记录。',attention:true }
const row = (phase: EvidenceExplanation['observed_fact']['phase'], reading = process, patch: Partial<EvidenceExplanation['observed_fact']> = {}): EvidenceExplanation => ({ ...source,source_label:'STRUCTURED_AUDIT_LOG',reading,observed_fact:{...source.observed_fact,level:'DIAGNOSIS_REQUIRED',phase,...patch} })

it('同源只显示一组，展开阶段并回传精确记录，辅助状态不使用通过色', () => {
  const initial=row('BASELINE',{kind:'REFERENCE',label:'操作前尚无本次事件',detail:'用于初始对照。',attention:false})
  const final=row('EVENTUAL');const click=vi.fn()
  render(<ObservationSources sources={[initial, row('AFTER'), final]} onEvidence={click}/> )
  expect(screen.getAllByRole('article')).toHaveLength(1)
  expect(screen.getByRole('article')).toHaveTextContent('诊断记录')
  expect(document.querySelector('.product-status')).toHaveAttribute('data-tone','neutral')
  const summary=screen.getByText('查看 3 个阶段');fireEvent.click(summary)
  expect(summary.closest('details')).toHaveAttribute('open')
  fireEvent.click(screen.getByRole('button',{name:'查看审计记录最终观察记录'}))
  expect(click).toHaveBeenCalledWith(final)
  expect(screen.queryByText(/阶段有记录缺口/)).not.toBeInTheDocument()
})

it('最终失败不被早期成功或恢复记录覆盖，已有缺口不被隐藏', () => {
  const values=[row('RECOVERY'),row('AFTER'),row('EVENTUAL',failure)]
  const groups=observationGroups(values)
  expect(groups[0].latest).toBe(values[2]);expect(groups[0].gaps).toEqual([values[2]])
  render(<ObservationSources sources={values} onEvidence={vi.fn()}/> )
  const article=screen.getByRole('article')
  expect(article.querySelector('.product-status')).toHaveTextContent('来源读取超时')
  expect(within(article).getByText(/1 个阶段有记录缺口/)).toBeInTheDocument()
  const recovered=observationGroups([row('AFTER',failure),row('EVENTUAL')])[0]
  expect(recovered.latest.reading?.kind).toBe('PROCESS');expect(recovered.gaps).toHaveLength(1)
})

it('相同来源不同效果、证明或等级分别保留，不串成同一条证据', () => {
  expect(observationGroups([row('AFTER'),row('EVENTUAL'),row('EVENTUAL',process,{effect_id:'other'}),row('EVENTUAL',process,{proof_fingerprint:'other'}),row('EVENTUAL',process,{level:'VERDICT_REQUIRED'})])).toHaveLength(4)
})

it('证据引用缺失时仍显示来源缺口，但不提供可用读取入口', () => {
  render(<ObservationSources sources={[{...row('EVENTUAL',failure),evidence_refs:[]}]} onEvidence={vi.fn()}/> )
  fireEvent.click(screen.getByText('查看 1 个阶段'))
  expect(screen.getByRole('button',{name:'查看审计记录最终观察记录'})).toBeDisabled()
})
