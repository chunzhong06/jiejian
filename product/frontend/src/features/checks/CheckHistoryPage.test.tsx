// 验证历史页只读取项目级 HistoryView，并使用后端状态文案。

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CheckHistoryPage } from './CheckHistoryPage'

const history = vi.hoisted(() => vi.fn())
vi.mock('../../api/results', () => ({ resultsApi: { history } }))

describe('CheckHistoryPage', () => {
  it('一次项目级请求展示本次未覆盖而不是已修复', async () => {
    history.mockResolvedValue({ project_id: 'project-demo', comparisons: [{ run_id: 'run-2', previous_run_id: 'run-1', checked_at_us: 2, policy_epoch: 6, policy_fingerprint: 'd'.repeat(64), relevant_intents: [{ intent_id: `pin_${'e'.repeat(32)}`, revision: 2, intent_hash: 'e'.repeat(64), display_label: 'P-001' }], change_verification: { change_id: `chg_${'f'.repeat(32)}`, required_intents: [{ intent_id: `pin_${'e'.repeat(32)}`, revision: 2, intent_hash: 'e'.repeat(64), display_label: 'P-001' }] }, changes: [{ finding_id: 'finding-1', title: '普通用户不应修改文档', subject_group: '普通用户账号', action: '修改', resource: '文档', relation: '拥有', status: 'NOT_COVERED', status_label: '本次未覆盖', explanation: '本次没有执行并充分证明这一权限要求，不能显示为已修复。', severity: 'high', evidence_refs: [], current_verdict: null, occurrence_status: 'DISAPPEARED' }] }] })
    render(<CheckHistoryPage projectId="project-demo" onError={vi.fn()} />)
    expect(await screen.findByText('本次未覆盖')).toBeInTheDocument()
    expect(screen.getByText('普通用户账号 · 修改 · 文档 · 拥有')).toBeInTheDocument()
    expect(screen.getByText(/不能显示为已修复/)).toBeInTheDocument()
    expect(screen.queryByText('已修复')).not.toBeInTheDocument()
    expect(screen.queryByText(/权限版本 6/)).not.toBeInTheDocument()
    expect(screen.getByText('本次检查由最近一次代码修改触发')).toBeInTheDocument()
    expect(screen.getByText('这次变化直接关联 1 条已确认权限要求')).toBeInTheDocument()
    expect(screen.queryByText(`chg_${'f'.repeat(32)}`)).not.toBeInTheDocument()
    expect(screen.queryByText('P-001')).not.toBeInTheDocument()
    expect(screen.queryByText(`pin_${'e'.repeat(32)}`)).not.toBeInTheDocument()
    expect(screen.queryByText('d'.repeat(64))).not.toBeInTheDocument()
    expect(screen.queryByText(`pin_${'e'.repeat(32)}@2:${'e'.repeat(64)}`)).not.toBeInTheDocument()
    expect(history).toHaveBeenCalledTimes(1)
    expect(history).toHaveBeenCalledWith('project-demo')
  })

  it('历史中的全范围检查不把零条直接关联写成零条权限要求', async () => {
    history.mockResolvedValue({ project_id: 'project-demo', intents: [], comparisons: [{ run_id: 'run-3', previous_run_id: 'run-2', checked_at_us: 3, policy_epoch: 6, policy_fingerprint: 'd'.repeat(64), relevant_intents: [], change_verification: { change_id: `chg_${'a'.repeat(32)}`, required_intents: [] }, changes: [{ finding_id: 'finding-2', title: '权限问题已解决', subject_group: '普通用户账号', action: '导出', resource: '项目包', relation: '其他权限组', status: 'FIXED', status_label: '已解决', explanation: '原违规后果已经消失。', severity: 'high', evidence_refs: [], current_verdict: 'SAFE', occurrence_status: 'DISAPPEARED' }] }] })
    render(<CheckHistoryPage projectId="project-demo" onError={vi.fn()} />)
    expect(await screen.findByText('这次变化未直接关联单条权限要求；仍按当前完整权限范围检查')).toBeInTheDocument()
    expect(screen.queryByText(/确认的 0 条权限要求/)).not.toBeInTheDocument()
  })

  it('默认按权限要求区分可靠关联与策略成员关系', async () => {
    const hash = 'a'.repeat(64)
    history.mockResolvedValue({
      project_id: 'project-demo',
      intents: [{
        intent_id: `pin_${'1'.repeat(32)}`,
        display_label: 'P-001',
        revisions: [{ revision: 2, intent_hash: hash, policy_epoch: 4, effective_state: 'ACTIVE', business_statement: '成员账号不可以修改负责人的文档。', approved_by: '本机用户', approved_at_us: 2 }],
        runs: [
          { run_id: 'run-exact', checked_at_us: 3, revision: 2, intent_hash: hash, policy_epoch: 4, association_status: 'EXACT', association_note: '本轮只依据这一条权限要求，可以可靠关联结果与诊断。', verdict: 'BLOCK', diagnosis_summary: '权限判断发生过晚。', change_revalidation: true, repair_status: null },
          { run_id: 'run-policy', checked_at_us: 4, revision: 2, intent_hash: hash, policy_epoch: 4, association_status: 'POLICY_ONLY', association_note: '本轮权限快照包含这条要求，但聚合结果无法可靠归到单条要求。', verdict: null, diagnosis_summary: null, change_revalidation: false, repair_status: null },
        ],
      }],
      comparisons: [],
    })
    render(<CheckHistoryPage projectId="project-demo" onError={vi.fn()} />)

    expect(await screen.findByText('P-001')).toBeInTheDocument()
    expect(screen.getByText('成员账号不可以修改负责人的文档。')).toBeInTheDocument()
    expect(screen.getByText('可可靠关联')).toBeInTheDocument()
    expect(screen.getByText('仅确认属于本轮策略')).toBeInTheDocument()
    expect(screen.getByText('发现可能的权限越界，需要处理')).toBeInTheDocument()
    expect(screen.getByText(/无法可靠归到单条要求/)).toBeInTheDocument()
    expect(screen.queryByText(hash)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /查看 1 个权限版本/ }))
    expect(screen.getByText(/由 本机用户 确认/)).toBeInTheDocument()
  })
})
