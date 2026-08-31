// 验证项目概览展示持续安全基线、并行待办和官方示例入口。

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ProductStatusDto, ProjectReadinessDto } from '../../api/projects'
import { WorkbenchPage } from './WorkbenchPage'

const readiness: ProjectReadinessDto = {
  project_id: 'p1', project_status: 'READY', application_connected: true,
  endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED',
  discovered_role_count: 3, confirmed_role_count: 2,
  discovered_action_count: 4, confirmed_action_count: 3,
  execution_profile_available: true, completed_flow_available: true,
  active_contract_available: true, current_scope_runnable: true,
  remaining_gap_count: 0, active_tasks: [], latest_verified_run_id: 'run-current',
  next_required_action: 'OPEN_RESULT',
}

const areas: ProductStatusDto['areas'] = [
  { key: 'overview', label: '项目概览', description: '查看基线', route: '/workspace', status: 'READY', status_label: '当前概览' },
  { key: 'changes', label: '变化与待办', description: '查看变化', route: '/changes', status: 'NEEDS_ATTENTION', status_label: '需要处理' },
  { key: 'permissions', label: '权限规则', description: '维护规则', route: '/permissions', status: 'NEEDS_ATTENTION', status_label: '需要确认' },
  { key: 'preparation', label: '测试准备', description: '准备条件', route: '/preparation', status: 'READY', status_label: '测试条件可用' },
  { key: 'validation', label: '验证运行', description: '运行检查', route: '/validation', status: 'READY', status_label: '可以检查' },
  { key: 'results', label: '结果与历史', description: '查看结果', route: '/results', status: 'AVAILABLE', status_label: '已有可信结果' },
]

const status: ProductStatusDto = {
  project: { project_id: 'p1', name: '演示应用', status: 'READY', target_type: 'WEB' },
  readiness,
  revalidation: {
    project_id: 'p1', status: 'REVIEW_REQUIRED', change_id: `chg_${'1'.repeat(32)}`,
    summary: '有 1 条权限规则需要重新确认。', next_path: '/permissions', next_label: '确认权限实现',
    required_intent_count: 1, reason_codes: ['MAPPING_REVIEW_REQUIRED'],
    verified_run_id: null, verified_change_id: null,
  },
  areas,
  attention_items: [
    { key: 'review-change-mapping', label: '重新确认权限规则与当前实现', description: '有 1 条规则需要确认。', route: '/permissions', tone: 'WARNING' },
    { key: 'verify-latest-change', label: '检查最近一次代码变化', description: '按完整权限范围运行。', route: '/validation', tone: 'ACTION' },
  ],
  latest_change: {
    change_id: `chg_${'1'.repeat(32)}`, project_id: 'p1', reason: 'Agent 增加导出能力', created_at_us: 1,
    status: 'COMPARABLE', complete: true, actual_changed_path_count: 2,
    added_count: 1, modified_count: 1, removed_count: 0, claimed_paths: [],
    added_paths: ['app/export.py'], modified_paths: ['app/permissions.py'], removed_paths: [],
    directly_affected_count: 1, mapping_review_required_count: 1, no_direct_evidence_count: 0,
    review_intent_ids: [`pin_${'2'.repeat(32)}`], summary: '有 1 条权限规则需要重新确认。', next_path: '/permissions',
  },
  latest_result: { run_id: 'run-current', verdict: 'BLOCK', headline: '发现权限问题', scope_statement: '当前范围已检查。', verified_change_id: null },
}

const officialExperience = { available: true, display_name: '协作空间', unavailable_reason: null, active: false, experience_id: null, experience_mode: null, project_id: null, origin: null, identities_ready: false, authorization_order: null, blob_observation: null, repair_change_id: null }

const common = {
  runs: [],
  systemStatus: { api: 'available' as const, worker: 'running' as const, browser: 'available' as const },
  experience: officialExperience,
  experienceBusy: false,
  onStartExperience: vi.fn().mockResolvedValue(true),
}

describe('WorkbenchPage', () => {
  it('同时展示全部待办，不再生成唯一下一步', () => {
    const onNavigate = vi.fn()
    render(<WorkbenchPage {...common} selected={{ project_id: 'p1', name: '演示应用' }} readiness={readiness} status={status} onNavigate={onNavigate} />)
    expect(screen.getByText('项目概览')).toBeInTheDocument()
    expect(screen.getByText('重新确认权限规则与当前实现')).toBeInTheDocument()
    expect(screen.getByText('检查最近一次代码变化')).toBeInTheDocument()
    expect(screen.queryByText('唯一下一步')).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: /打\s*开/ })[0])
    expect(onNavigate).toHaveBeenCalledWith('/permissions')
  })

  it('展示最近变化并进入完整变化记录', () => {
    const onNavigate = vi.fn()
    render(<WorkbenchPage {...common} selected={{ project_id: 'p1', name: '演示应用' }} readiness={readiness} status={status} onNavigate={onNavigate} />)
    expect(screen.getByText('Agent 增加导出能力')).toBeInTheDocument()
    expect(screen.getByText(/实际确认 2 个文件变化/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '查看变化记录' }))
    expect(onNavigate).toHaveBeenCalledWith('/changes')
  })

  it('空工作区说明持续基线而不是六步接入', () => {
    render(<WorkbenchPage {...common} selected={null} readiness={null} status={null} onNavigate={vi.fn()} />)
    expect(screen.getByText('建立第一份权限安全基线')).toBeInTheDocument()
    expect(screen.getByText(/应用继续开发时/)).toBeInTheDocument()
    expect(screen.queryByText(/六个连续步骤/)).not.toBeInTheDocument()
  })

  it('官方示例仍由用户明确同意后启动', () => {
    render(<WorkbenchPage {...common} selected={null} readiness={null} status={null} onNavigate={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '启动官方示例' }))
    expect(screen.getByText('启动官方示例？')).toBeInTheDocument()
    expect(screen.getByText(/不会开始真实检查/)).toBeInTheDocument()
  })
})
