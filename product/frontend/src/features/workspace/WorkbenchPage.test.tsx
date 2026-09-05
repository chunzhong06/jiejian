// 验证工作台只消费服务端动作级 WorkspaceView，并忠实执行唯一 PrimaryTask。

import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { WorkspaceViewDto } from '../../api/workspace'
import { WorkbenchPage } from './WorkbenchPage'

const experience = {
  available: false, display_name: '协作空间', unavailable_reason: '当前不可用', active: false,
  experience_id: null, project_id: null, origin: null, scenario_prepared: false,
  scenario_version: null, vulnerable_change_id: null, repair_change_id: null,
}

const workspace: WorkspaceViewDto = {
  project: { project_id: 'p1', name: '演示应用', status: 'READY', target_type: 'WEB' },
  connection: { endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED' },
  actors: [],
  actions: [{
    action_id: `bac_${'1'.repeat(32)}`, action_revision: 2, display_name: '导出交付包',
    description: '导出完整交付内容', effect_catalog: [], current_permissions: [],
    permission_status: {
      action_id: `bac_${'1'.repeat(32)}`, action_revision: 2,
      permission_semantics_confirmed: false, active_permission_count: 0, stale_permission_count: 1,
      allow_control_available: false, validation_contract_complete: false,
      reason_codes: ['PERMISSION_REVISION_REVIEW_REQUIRED'],
    },
    implementation: {
      action_id: `bac_${'1'.repeat(32)}`, action_revision: 2,
      binding_exists: true, basis_version: 1, source_candidate_ids: [`action_${'2'.repeat(32)}`],
      status: 'STALE', reason_codes: ['SOURCE_FINGERPRINT_CHANGED'], binding_fingerprint: 'b'.repeat(64),
      source_proposal_id: `bpr_${'3'.repeat(32)}`, confirmed_at_us: 1,
      bound_understanding_revision: 1, current_understanding_revision: 2,
      changed_candidate_ids: [`action_${'2'.repeat(32)}`],
    },
    subject_actor_ids: [], actor_implementation_issue_count: 0,
  }],
  primary_task: {
    task_id: 'ptk_test', task_kind: 'REVIEW_PERMISSION_REVISION',
    business_action_id: `bac_${'1'.repeat(32)}`, business_actor_id: null,
    title: '重新确认“导出交付包”的权限', why_now: '当前动作已形成新 revision。',
    user_responsibility: '确认当前允许与拒绝规则。', system_will_do: '保存新的权限 revision。',
    route: '/permissions', can_execute: true, stale_fingerprint: 'f'.repeat(64),
  },
  areas: [
    { key: 'overview', label: '工作台', description: '查看当前工作区', route: '/workspace', status: 'NEEDS_ATTENTION', status_label: '需要处理' },
    { key: 'permissions', label: '权限', description: '维护业务边界', route: '/permissions', status: 'NEEDS_ATTENTION', status_label: '需要确认' },
    { key: 'changes', label: '变化', description: '当前未接入', route: '/changes', status: 'BLOCKED', status_label: '当前不可用' },
    { key: 'tests', label: '测试', description: '当前未接入', route: '/tests', status: 'BLOCKED', status_label: '当前不可检查' },
  ],
}

const systemStatus = { api: 'available' as const, worker: 'unavailable' as const, browser: 'available' as const }

describe('WorkbenchPage', () => {
  it('直接展示并执行服务端 PrimaryTask', () => {
    const onNavigate = vi.fn()
    render(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用' }} workspace={workspace} systemStatus={systemStatus} experience={experience} onNavigate={onNavigate} />)

    expect(screen.getByRole('heading', { name: '当前动作已形成新 revision。' })).toBeInTheDocument()
    expect(screen.getByText('重新确认“导出交付包”的权限')).toBeInTheDocument()
    expect(screen.getByText('系统接下来会：保存新的权限 revision。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '前往处理' }))
    expect(onNavigate).toHaveBeenCalledWith('/permissions')
  })

  it('不读取 dormant Run 伪造结果，并汇总动作级复核状态', () => {
    render(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用' }} workspace={workspace} systemStatus={systemStatus} experience={experience} onNavigate={vi.fn()} />)

    expect(within(screen.getByLabelText('最近可信结果')).getByText('新的检查结果尚未重新接入')).toBeInTheDocument()
    expect(screen.getByText('1 项当前业务动作')).toBeInTheDocument()
    expect(screen.getByText('1 项需要确认当前权限或代码实现。')).toBeInTheDocument()
    expect(screen.getByText('当前不可检查')).toBeInTheDocument()
  })

  it('空工作区只提供应用接入，不启动旧示例状态机', () => {
    render(<WorkbenchPage selected={null} workspace={null} systemStatus={systemStatus} experience={experience} onNavigate={vi.fn()} />)

    expect(screen.getByText('建立第一份权限安全基线')).toBeInTheDocument()
    expect(screen.getByText('当前不可用')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '启动官方示例' })).not.toBeInTheDocument()
  })
})
