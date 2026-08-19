import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { EvidenceTimeline } from './EvidenceTimeline'

const resultsApi = vi.hoisted(() => ({ evidenceDetail: vi.fn() }))
vi.mock('../../api/results', () => ({ resultsApi }))

describe('EvidenceTimeline', () => {
  afterEach(() => cleanup())

  it.each([
    { name: 'fixed', verdict: 'SAFE', verdictText: '当前规则覆盖范围内未发现越权', outcome: 'DENIED', effect: 'ABSENT', complete: true, reliable: true, outcomeText: '执行已拒绝', effectText: '资源状态未变化', completeness: '完整', reliability: '可靠', reasonCodes: [] },
    { name: 'vulnerable', verdict: 'VULNERABLE', verdictText: '发现可能的权限越界，需要处理', outcome: 'DENIED', effect: 'CONFIRMED', complete: true, reliable: true, outcomeText: '执行已拒绝', effectText: '资源状态发生变化', completeness: '完整', reliability: '可靠', reasonCodes: [] },
    { name: 'inconclusive', verdict: 'INCONCLUSIVE', verdictText: '证据不足，暂时不能下结论', outcome: 'UNKNOWN', effect: 'UNKNOWN', complete: false, reliable: false, outcomeText: '执行结果无法确定', effectText: '无法可靠获取资源状态', completeness: '未完成', reliability: '不可靠', reasonCodes: ['OBSERVATION_INCOMPLETE'] },
  ])('按三态当前事实展示检查对象、执行事实和真实观察：$name', async ({ verdict, verdictText, outcome, effect, complete, reliable, outcomeText, effectText, completeness, reliability, reasonCodes }) => {
    resultsApi.evidenceDetail.mockResolvedValue({
      evidence_id: 'ev-current',
      case_snapshot: { subject_id: 'alice', action_id: 'modify', resource_ids: ['doc-1'], required_observations: ['resource_state'] },
      execution_fact: { target_type: 'WEB', action_id: 'modify', outcome, reason_codes: [] },
      observation_facts: [{ requirement_id: 'resource_state', resource_id: 'doc-1', effect, complete, reliable, reason_codes: reasonCodes }],
      observations: [],
      outcomes: [],
      verdict,
    })
    render(<EvidenceTimeline runId="run-current" evidence={[{ evidence_id: 'ev-current' }]} onError={vi.fn()} />)
    expect(await screen.findByText('检查对象')).toBeInTheDocument()
    expect(screen.getByText('执行事实')).toBeInTheDocument()
    expect(screen.getByText('真实观察')).toBeInTheDocument()
    expect(screen.getByText('确定性结论')).toBeInTheDocument()
    expect(screen.queryByText('请求事实')).not.toBeInTheDocument()
    expect(screen.queryByText('多面观察')).not.toBeInTheDocument()
    expect(screen.getAllByText('修改')).toHaveLength(2)
    expect(screen.getByText(outcomeText)).toBeInTheDocument()
    expect(screen.getByText(effectText)).toBeInTheDocument()
    expect(screen.getByText(completeness)).toBeInTheDocument()
    expect(screen.getByText(reliability)).toBeInTheDocument()
    expect(screen.getByText(verdictText)).toBeInTheDocument()
    expect(screen.getByText('高级：技术详情')).toBeInTheDocument()
  })

  it('在高级技术详情中将 EVENTUAL 显示为最终状态', async () => {
    resultsApi.evidenceDetail.mockResolvedValue({
      evidence_id: 'ev-eventual',
      case_snapshot: { subject_id: 'alice', action_id: 'modify', resource_ids: ['doc-1'], required_observations: ['resource_state'] },
      execution_fact: { target_type: 'WEB', action_id: 'modify', outcome: 'DENIED', reason_codes: [] },
      observation_facts: [{ requirement_id: 'resource_state', resource_id: 'doc-1', effect: 'ABSENT', complete: true, reliable: true, reason_codes: [] }],
      observations: [{ observer_id: 'owner_api', observer_type: 'OWNER_API', phase: 'EVENTUAL', target_id: 'doc-1', completeness: 'COMPLETE', causality: 'CORRELATED', state: { canonical_data: { value: 'unchanged' } } }],
      outcomes: [],
      verdict: 'PASS',
    })
    render(<EvidenceTimeline runId="run-eventual" evidence={[{ evidence_id: 'ev-eventual' }]} onError={vi.fn()} />)
    fireEvent.click(await screen.findByText('高级：技术详情'))
    expect(await screen.findByText('最终状态')).toBeInTheDocument()
  })
})
