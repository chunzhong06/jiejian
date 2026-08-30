// 验证历史页只读取项目级 HistoryView，并使用后端状态文案。

import { render, screen } from '@testing-library/react'
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
    expect(screen.getByText('本次检查依据权限版本 6')).toBeInTheDocument()
    expect(screen.getByText(`代码变化重验 chg_${'f'.repeat(32)} · 需要重验的权限：P-001`)).toBeInTheDocument()
    expect(screen.queryByText(`pin_${'e'.repeat(32)}`)).not.toBeInTheDocument()
    expect(screen.queryByText('d'.repeat(64))).not.toBeInTheDocument()
    expect(screen.queryByText(`pin_${'e'.repeat(32)}@2:${'e'.repeat(64)}`)).not.toBeInTheDocument()
    expect(history).toHaveBeenCalledTimes(1)
    expect(history).toHaveBeenCalledWith('project-demo')
  })
})
