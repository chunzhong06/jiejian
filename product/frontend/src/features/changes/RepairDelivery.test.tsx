// 修复阅读面保留全部正常业务，七态以服务端为准，不能用变化登记推断成功。
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RepairDelivery, type RepairTask } from './RepairDelivery'
import type { RepairComparisonRow, RepairStatus } from '../../api/repairs'
const row = (role: RepairComparisonRow['role'], id: string): RepairComparisonRow => ({ role, source_case_id: id, action_label: id === 'read' ? '读取资料' : '导出资料', subject_label: '成员', resource_owner_label: '负责人', resource_id: 'resource', effect_labels: ['资料生成'], before_verdict: 'SAFE', before_evidence_refs: [], match_status: 'NOT_AVAILABLE' })
const task = (status: RepairStatus): RepairTask => ({ task_reference: 'task', status, change_id: 'chg', run_id: null, verification: null,
  contract: { project_id: 'p1', source_run_id: 'run-old', source_case_id: 'deny', repair_fingerprint: 'repair', original_policy_epoch: 1, deny: { identity: { action_id: 'action', resource_id: 'resource', subject_test_identity_id: 'subject', resource_owner_test_identity_id: 'owner', protected_effect_ids: ['effect'] }, evidence_refs: [] }, regressions: [{ source_case_id: 'read' }] },
  comparison: [row('DENY', 'deny'), row('SELECTED_ALLOW', 'allow'), row('REGRESSION', 'read')] })
describe('修复要求与交付', () => {
  it.each<RepairStatus>(['REPAIR_REQUIRED', 'CHANGE_SUBMITTED', 'READY_TO_VERIFY', 'VERIFIED', 'NOT_VERIFIED', 'INCONCLUSIVE', 'STALE'])('遵守 %s 状态，不从已登记修改推断通过', status => {
    render(<RepairDelivery task={task(status)} onNavigate={vi.fn()} onBack={vi.fn()} onViewChange={vi.fn()}/>)
    expect(screen.getByRole('heading', { name: '需要消除的后果' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '必须保留的正常业务' })).toBeInTheDocument()
    expect(screen.getAllByText(/读取资料/).length).toBeGreaterThan(0)
    if (status === 'VERIFIED') expect(screen.getByText('原题与要求保留的业务通过验证')).toBeInTheDocument()
    else expect(screen.queryByText('原题与要求保留的业务通过验证')).not.toBeInTheDocument()
  })
  it('回到精确原题和本批修改，尚未发布的 Run 只称记录', () => {
    const onNavigate = vi.fn()
    render(<RepairDelivery task={{ ...task('CHANGE_SUBMITTED'), run_id: 'pending' }} onNavigate={onNavigate} onBack={vi.fn()} onViewChange={vi.fn()}/>)
    fireEvent.click(screen.getByRole('button', { name: '查看原始证据' }))
    expect(onNavigate).toHaveBeenCalledWith('/history?run_id=run-old&case_id=deny')
    fireEvent.click(screen.getByRole('button', { name: '查看关联检查记录' }))
    expect(onNavigate).toHaveBeenCalledWith('/history?run_id=pending')
    expect(screen.queryByRole('button', { name: '查看关联复验结果' })).not.toBeInTheDocument()
  })
})
