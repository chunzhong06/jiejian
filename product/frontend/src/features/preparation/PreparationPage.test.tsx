// 验证测试准备按当前事实展示账号、流程和检查配置，不把缺失数据误报为可用。

import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ProjectReadinessDto } from '../../api/projects'
import { PreparationPage } from './PreparationPage'

const baseReadiness: ProjectReadinessDto = {
  project_id: 'p1', project_status: 'READY', application_connected: true,
  endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED',
  discovered_role_count: 2, confirmed_role_count: 2,
  discovered_action_count: 1, confirmed_action_count: 1,
  execution_profile_available: false, completed_flow_available: false,
  active_contract_available: false, current_scope_runnable: false,
  remaining_gap_count: 3, active_tasks: [], latest_verified_run_id: null,
  next_required_action: 'RECORD_FLOW',
}

describe('PreparationPage', () => {
  it('权限动作尚未形成时不把测试账号误报为可用', () => {
    render(<PreparationPage readiness={baseReadiness} onNavigate={vi.fn()} />)

    expect(screen.getByText('0/3 项可用')).toBeInTheDocument()
    const accountCard = screen.getByText('测试账号').closest('.ant-card')!
    expect(within(accountCard as HTMLElement).getByText('需要处理')).toBeInTheDocument()
  })

  it('三类准备事实齐备后仍允许分别维护并进入验证', () => {
    const onNavigate = vi.fn()
    const readiness: ProjectReadinessDto = {
      ...baseReadiness,
      permission_actions: [{ action_candidate_id: 'action-1', action_display_name: '导出完整包', compilable: true, gaps: [], required_intent_count: 2, confirmed_intent_count: 2, executable_intent_count: 2, representative_gap_count: 0 }],
      execution_profile_available: true,
      completed_flow_available: true,
      active_contract_available: true,
      current_scope_runnable: true,
      remaining_gap_count: 0,
      next_required_action: 'RUN_CHECK',
    }
    render(<PreparationPage readiness={readiness} onNavigate={onNavigate} />)

    expect(screen.getByText('3/3 项可用')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '管理测试账号' }))
    fireEvent.click(screen.getByRole('button', { name: '管理业务流程' }))
    fireEvent.click(screen.getAllByRole('button', { name: '前往验证运行' })[0])
    expect(onNavigate).toHaveBeenNthCalledWith(1, '/identities')
    expect(onNavigate).toHaveBeenNthCalledWith(2, '/flows')
    expect(onNavigate).toHaveBeenNthCalledWith(3, '/validation')
  })
})
