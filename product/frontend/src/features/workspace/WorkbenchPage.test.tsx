// 验证工作台突出后端指定的主任务，并连接变化、权限、测试三个独立模块。

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ProductStatusDto, ProjectReadinessDto } from '../../api/projects'
import { WorkbenchPage } from './WorkbenchPage'

const api = vi.hoisted(() => ({ deliveryCheck: vi.fn() }))
vi.mock('../../api/projects', () => ({ projectsApi: { deliveryCheck: api.deliveryCheck } }))

const readiness: ProjectReadinessDto = {
  project_id: 'p1', project_status: 'READY', application_connected: true,
  endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED',
  discovered_role_count: 3, confirmed_role_count: 2,
  discovered_action_count: 4, confirmed_action_count: 3,
  execution_profile_available: true, completed_flow_available: true,
  active_contract_available: true, current_scope_runnable: true,
  confirmed_permission_requirement_count: 2, permission_representative_gap_count: 0,
  remaining_gap_count: 0, active_tasks: [], latest_verified_run_id: 'run-current',
  next_required_action: 'OPEN_RESULT',
}

const areas: ProductStatusDto['areas'] = [
  { key: 'overview', label: '工作台', description: '查看全局状态', route: '/workspace', status: 'READY', status_label: '持续更新' },
  { key: 'changes', label: '变化', description: '核对 Agent 修改', route: '/changes', status: 'NEEDS_ATTENTION', status_label: '需要处理' },
  { key: 'permissions', label: '权限', description: '维护权限边界', route: '/permissions', status: 'NEEDS_ATTENTION', status_label: '需要确认' },
  { key: 'tests', label: '测试', description: '准备、运行与结果', route: '/tests', status: 'AVAILABLE', status_label: '已有可信结果' },
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
  primary_attention_key: 'review-change-mapping',
  attention_items: [
    { key: 'review-change-mapping', label: '重新确认权限规则与当前实现', description: '有 1 条规则需要确认。', route: '/permissions', tone: 'WARNING' },
    { key: 'verify-latest-change', label: '检查最近一次代码变化', description: '按完整权限范围运行。', route: '/validation', tone: 'ACTION' },
  ],
  latest_change: {
    change_id: `chg_${'1'.repeat(32)}`, project_id: 'p1', reason: 'Agent 增加导出能力', submitted_by: 'MCP · Codex', created_at_us: 1,
    status: 'COMPARABLE', complete: true, actual_changed_path_count: 2,
    added_count: 1, modified_count: 1, removed_count: 0, claimed_paths: [],
    added_paths: ['app/export.py'], modified_paths: ['app/permissions.py'], removed_paths: [],
    directly_affected_count: 1, mapping_review_required_count: 1, no_direct_evidence_count: 0,
    review_intent_ids: [`pin_${'2'.repeat(32)}`], summary: '有 1 条权限规则需要重新确认。', next_path: '/permissions',
  },
  latest_result: { run_id: 'run-current', verdict: 'BLOCK', headline: '发现权限问题', scope_statement: '当前范围已检查。', verified_change_id: null },
  inconclusive_recovery: null,
  repair: null,
}

const officialExperience = { available: true, display_name: '协作空间', unavailable_reason: null, active: false, experience_id: null, project_id: null, origin: null, scenario_prepared: false, scenario_version: null, vulnerable_change_id: null, repair_change_id: null }

const common = {
  runs: [],
  systemStatus: { api: 'available' as const, worker: 'unavailable' as const, browser: 'available' as const },
  experience: officialExperience,
  experienceBusy: false,
  onStartExperience: vi.fn().mockResolvedValue(true),
  onPrepareExperience: vi.fn(),
  onRunExperience: vi.fn(),
  onSwitchExperience: vi.fn(),
}

describe('WorkbenchPage', () => {
  it('只突出后端显式指定的主任务，不从待办列表位置另猜优先级', () => {
    const onNavigate = vi.fn()
    render(<WorkbenchPage {...common} selected={{ project_id: 'p1', name: '演示应用' }} readiness={readiness} status={status} onNavigate={onNavigate} onError={vi.fn()} />)
    expect(screen.getByRole('heading', { name: '演示应用' })).toBeInTheDocument()
    expect(screen.getByText('有 1 条规则需要确认。')).toBeInTheDocument()
    expect(screen.queryByText('检查最近一次代码变化')).not.toBeInTheDocument()
    expect(screen.getByText('另有 1 项状态已归入下方对应区域。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重新确认权限规则与当前实现' }))
    expect(onNavigate).toHaveBeenCalledWith('/permissions')
  })

  it('把变化、权限和检查作为并列领域，并删除普通应用中的示例与重复 AI 入口', () => {
    const onNavigate = vi.fn()
    render(<WorkbenchPage {...common} selected={{ project_id: 'p1', name: '演示应用' }} readiness={readiness} status={status} onNavigate={onNavigate} onError={vi.fn()} />)
    expect(screen.getByText('Agent 增加导出能力')).toBeInTheDocument()
    expect(screen.getByText('2 个文件发生变化')).toBeInTheDocument()
    expect(screen.getByText('2 条已确认规则')).toBeInTheDocument()
    expect(screen.getByText('变化与修复')).toBeInTheDocument()
    expect(screen.getByText('权限边界')).toBeInTheDocument()
    expect(screen.getByText('检查与结果')).toBeInTheDocument()
    const trustedResult = screen.getByLabelText('最近可信结果')
    expect(within(trustedResult).getByRole('heading', { name: '发现权限问题' })).toBeInTheDocument()
    expect(within(trustedResult).getByText('当前范围已检查。')).toBeInTheDocument()
    expect(screen.queryByText('AI 工具')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '启动官方示例' })).not.toBeInTheDocument()
    expect(screen.queryByText('运行环境中有服务暂不可用，查看详情')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '进入变化与修复' }))
    expect(onNavigate).toHaveBeenCalledWith('/changes')
  })

  it('主任务引用失配时停止生成导航动作', () => {
    render(<WorkbenchPage {...common} selected={{ project_id: 'p1', name: '演示应用' }} readiness={readiness} status={{ ...status, primary_attention_key: 'missing' }} onNavigate={vi.fn()} onError={vi.fn()} />)
    expect(screen.getByText('当前主任务无法与待办事实对应，请刷新后重试。')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重新确认权限规则与当前实现' })).not.toBeInTheDocument()
  })

  it('当前应用确为官方示例且有可信结果时才提供一键完整展示', () => {
    const onEnterPresentation = vi.fn()
    const activeExperience = { ...officialExperience, active: true, experience_id: `exp_${'a'.repeat(32)}`, project_id: 'p1', scenario_prepared: true, scenario_version: 'VULNERABLE' as const, scenario_changed_at_us: 1 }
    render(<WorkbenchPage {...common} runs={[{ run_id: 'run-current', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED', created_at_us: 2 }]} experience={activeExperience} selected={{ project_id: 'p1', name: '协作空间' }} readiness={readiness} status={status} onEnterPresentation={onEnterPresentation} onNavigate={vi.fn()} onError={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '进入完整展示' }))
    expect(onEnterPresentation).toHaveBeenCalledOnce()
  })

  it('空工作区说明持续基线而不是六步接入', () => {
    render(<WorkbenchPage {...common} selected={null} readiness={null} status={null} onNavigate={vi.fn()} onError={vi.fn()} />)
    expect(screen.getByText('建立第一份权限安全基线')).toBeInTheDocument()
    expect(screen.getByText(/应用继续开发时/)).toBeInTheDocument()
    expect(screen.queryByText(/六个连续步骤/)).not.toBeInTheDocument()
  })

  it('官方示例仍由用户明确同意后启动', () => {
    render(<WorkbenchPage {...common} selected={null} readiness={null} status={null} onNavigate={vi.fn()} onError={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '启动官方示例' }))
    expect(screen.getByText('进入 Agent 写错的问题版？')).toBeInTheDocument()
    expect(screen.getByText(/不会开始真实检查/)).toBeInTheDocument()
  })

  it('明确说明新检查与交付主链当前不可用，不调用旧交付入口', () => {
    render(<WorkbenchPage {...common} selected={{ project_id: 'p1', name: '演示应用' }} readiness={readiness} status={status} onNavigate={vi.fn()} onError={vi.fn()} />)

    expect(api.deliveryCheck).not.toHaveBeenCalled()
    expect(screen.getByText('当前版本暂不执行交付检查')).toBeInTheDocument()
    expect(screen.getByText(/不会用旧 Permission 适配器/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '交付前检查' })).not.toBeInTheDocument()
  })
})
