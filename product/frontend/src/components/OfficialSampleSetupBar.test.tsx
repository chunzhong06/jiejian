// 验证官方样例状态区只配置场景、切换真实版本和进入检查，不由按钮伪造结论。

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { OfficialSampleSetupBar } from './OfficialSampleSetupBar'

const experience = {
  available: true,
  display_name: '协作空间',
  unavailable_reason: null,
  active: true,
  experience_id: `exp_${'a'.repeat(32)}`,
  project_id: 'p1',
  origin: 'http://127.0.0.1:12345',
  scenario_prepared: false,
  scenario_version: 'VULNERABLE' as const,
  vulnerable_change_id: null,
  repair_change_id: null,
}

function status(withResult = false) {
  return {
    project: { project_id: 'p1', name: '协作空间', status: 'DRAFT', target_type: 'WEB' as const },
    readiness: null,
    areas: [],
    primary_attention_key: null,
    attention_items: [],
    latest_change: null,
    latest_result: withResult ? { run_id: 'run-block', verdict: 'BLOCK', headline: '发现权限问题', scope_statement: '当前范围已检查。', verified_change_id: null } : null,
  }
}

describe('OfficialSampleSetupBar', () => {
  it('未准备时只提供一键应用公开样例合同', () => {
    const prepare = vi.fn()
    render(<OfficialSampleSetupBar status={status() as never} experience={experience} busy={false} onPrepare={prepare} onRun={vi.fn()} onSwitchVersion={vi.fn()} />)
    expect(screen.getByText('样例已经启动，等待应用公开设计合同')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '一键应用样例配置' }))
    expect(prepare).toHaveBeenCalledOnce()
    expect(screen.queryByRole('button', { name: '检查问题版' })).not.toBeInTheDocument()
  })

  it('准备完成后切换证据受限版前解释证据边界', () => {
    const switchVersion = vi.fn()
    render(<OfficialSampleSetupBar status={status() as never} experience={{ ...experience, scenario_prepared: true }} busy={false} onPrepare={vi.fn()} onRun={vi.fn()} onSwitchVersion={switchVersion} />)
    fireEvent.click(screen.getByRole('button', { name: '证据受限实验' }))
    expect(screen.getByText('进入证据受限实验？')).toBeInTheDocument()
    expect(screen.getByText(/证据不足时只能暂时不下结论/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认切换' }))
    expect(switchVersion).toHaveBeenCalledWith('EVIDENCE_LIMITED', undefined)
  })

  it('修复入口展示 Agent 获得的具体合同并引用 BLOCK 结果', () => {
    const switchVersion = vi.fn()
    render(<OfficialSampleSetupBar status={status(true) as never} experience={{ ...experience, scenario_prepared: true }} busy={false} sourceBlockRunId="run-block" onPrepare={vi.fn()} onRun={vi.fn()} onSwitchVersion={switchVersion} />)
    fireEvent.click(screen.getByRole('button', { name: '交给 Agent 修复' }))
    expect(screen.getByText('把界鉴修复意见交给 Agent？')).toBeInTheDocument()
    expect(screen.getByText(/Bob 的导出任务、队列消息和 ZIP 文件/)).toBeInTheDocument()
    expect(screen.getByText(/authorization_policy.py/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '生成修改并切换' }))
    expect(switchVersion).toHaveBeenCalledWith('FIXED', 'run-block')
  })

  it('没有 BLOCK 来源时不能把问题版直接切成修复版', () => {
    render(<OfficialSampleSetupBar status={status() as never} experience={{ ...experience, scenario_prepared: true }} busy={false} onPrepare={vi.fn()} onRun={vi.fn()} onSwitchVersion={vi.fn()} />)
    expect(screen.getByRole('button', { name: '交给 Agent 修复' })).toBeDisabled()
  })

  it('未启动示例或当前项目不匹配时不显示状态区', () => {
    const props = { status: status() as never, experience, busy: false, onPrepare: vi.fn(), onRun: vi.fn(), onSwitchVersion: vi.fn() }
    const { rerender } = render(<OfficialSampleSetupBar {...props} experience={{ ...experience, active: false }} />)
    expect(screen.queryByLabelText('官方样例状态')).not.toBeInTheDocument()
    rerender(<OfficialSampleSetupBar {...props} status={{ ...status(), project: { project_id: 'p2', name: '其他应用', status: 'DRAFT', target_type: 'WEB' } } as never} />)
    expect(screen.queryByLabelText('官方样例状态')).not.toBeInTheDocument()
  })
})
