// 验证业务边界页面只使用当前权限投影，并支持普通不可变提案与人工批准。

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BusinessBoundaryPage } from './BusinessBoundaryPage'

const mockApi = vi.hoisted(() => ({
  current: vi.fn(), preview: vi.fn(), proposals: vi.fn(), createProposal: vi.fn(),
  maintenanceDraft: vi.fn(), createMaintenanceProposal: vi.fn(), approve: vi.fn(), reject: vi.fn(),
}))

vi.mock('../../api/businessBoundaries', () => ({ businessBoundariesApi: mockApi }))

const project = { project_id: 'app_demo', name: '演示应用' }
const preview = {
  project_id: 'app_demo', application_understanding_revision: 2,
  candidates: [
    { candidate_kind: 'ROLE', candidate_id: `role_${'1'.repeat(32)}`, display_name: '项目负责人', confidence: 'HIGH' },
    { candidate_kind: 'ACTION', candidate_id: `action_${'2'.repeat(32)}`, display_name: '导出项目包', confidence: 'MEDIUM' },
    { candidate_kind: 'ACTION', candidate_id: `action_${'3'.repeat(32)}`, display_name: '可能的低置信动作', confidence: 'LOW' },
  ],
}
const command = {
  proposed_actors: [
    { item_id: 'pactr_1100000000000001', write_mode: 'CREATE', display_name: '项目负责人', description: '负责项目交付', effective_state: 'ACTIVE' },
    { item_id: 'pactr_1100000000000002', write_mode: 'CREATE', display_name: '普通协作成员', description: '参与日常协作', effective_state: 'ACTIVE' },
  ],
  proposed_actions: [
    { item_id: 'pactn_1100000000000001', write_mode: 'CREATE', display_name: '导出完整项目交付包', description: '形成交付包', primary_resource_concept: '项目交付空间', operation_kind: 'EXPORT', state_changing: true, effect_catalog: [{ item_id: 'peff_1100000000000001', business_label: '完整项目交付包真实形成', effect_kind: 'OBJECT_CREATION', resource_concept: '项目交付包', protected_projection: [], description: '交付包已经形成' }], effective_state: 'ACTIVE' },
    { item_id: 'pactn_1100000000000002', write_mode: 'CREATE', display_name: '查看日常协作资料', description: '读取有限资料', primary_resource_concept: '日常协作资料', operation_kind: 'READ', state_changing: false, effect_catalog: [{ item_id: 'peff_1100000000000002', business_label: '日常协作资料的有限内容可见', effect_kind: 'DATA_DISCLOSURE', resource_concept: '日常协作资料', protected_projection: ['material.title'], description: '只读取有限字段' }], effective_state: 'ACTIVE' },
  ],
  proposed_permissions: [
    { item_id: 'pperm_1100000000000001', write_mode: 'CREATE', effective_state: 'ACTIVE', subject_actor_item_id: 'pactr_1100000000000001', business_action_item_id: 'pactn_1100000000000001', resource_owner_actor_item_id: 'pactr_1100000000000001', relation: 'OWNS', expectation: 'ALLOW', protected_effect_item_ids: ['peff_1100000000000001'] },
    { item_id: 'pperm_1100000000000002', write_mode: 'CREATE', effective_state: 'ACTIVE', subject_actor_item_id: 'pactr_1100000000000002', business_action_item_id: 'pactn_1100000000000001', resource_owner_actor_item_id: 'pactr_1100000000000001', relation: 'OTHER_ROLE', expectation: 'DENY', protected_effect_item_ids: ['peff_1100000000000001'] },
    { item_id: 'pperm_1100000000000003', write_mode: 'CREATE', effective_state: 'ACTIVE', subject_actor_item_id: 'pactr_1100000000000002', business_action_item_id: 'pactn_1100000000000002', resource_owner_actor_item_id: 'pactr_1100000000000002', relation: 'OWNS', expectation: 'ALLOW', protected_effect_item_ids: ['peff_1100000000000002'] },
  ],
  unresolved_questions: [], provenance: '界鉴 1.1.0 官方公开业务合同',
}
const proposal = { ...command, proposal_id: `bpr_${'4'.repeat(32)}`, project_id: 'app_demo', source_snapshot: {}, proposal_fingerprint: '5'.repeat(64), created_at_us: 1 }
const emptyBoundary = { project_id: 'app_demo', policy_epoch: 0, actors: [], actions: [], actor_bindings: [], action_bindings: [], permission_intents: [], permission_statuses: [] }
const approvedBoundary: any = {
  project_id: 'app_demo', policy_epoch: 1,
  actors: command.proposed_actors.map((item, index) => ({ actor_id: `bar_${String(index + 1).repeat(32)}`, revision: 1, display_name: item.display_name, description: item.description, effective_state: 'ACTIVE' })),
  actions: command.proposed_actions.map((item, index) => ({ ...item, action_id: `bac_${String(index + 3).repeat(32)}`, revision: 1, effect_catalog: item.effect_catalog.map((effect, effectIndex) => ({ ...effect, effect_id: `bef_${String(index + effectIndex + 5).repeat(32)}` })) })),
  actor_bindings: [], action_bindings: [], permission_intents: [], permission_statuses: [],
}
approvedBoundary.permission_intents = command.proposed_permissions.map((item, index) => ({
  subject_actor_id: approvedBoundary.actors[item.subject_actor_item_id.endsWith('1') ? 0 : 1].actor_id,
  subject_actor_revision: 1,
  business_action_id: approvedBoundary.actions[item.business_action_item_id.endsWith('1') ? 0 : 1].action_id,
  action_revision: 1,
  resource_owner_actor_id: approvedBoundary.actors[item.resource_owner_actor_item_id.endsWith('1') ? 0 : 1].actor_id,
  resource_owner_actor_revision: 1,
  relation: item.relation,
  expectation: item.expectation,
  protected_effect_ids: [approvedBoundary.actions[item.business_action_item_id.endsWith('1') ? 0 : 1].effect_catalog[0].effect_id],
  effective_state: 'ACTIVE',
  _test_index: index,
}))
approvedBoundary.permission_statuses = approvedBoundary.actions.map((item: any) => ({ action_id: item.action_id, action_revision: 1, permission_semantics_confirmed: true, active_permission_count: 1, stale_permission_count: 0, allow_control_available: true, validation_contract_complete: false, reason_codes: ['VALIDATION_PIPELINE_DEFERRED_TO_1_1_3'] }))

describe('业务边界页面', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.current.mockResolvedValue(emptyBoundary)
    mockApi.preview.mockResolvedValue(preview)
    mockApi.proposals.mockResolvedValue({ project_id: 'app_demo', proposals: [] })
    mockApi.maintenanceDraft.mockResolvedValue({
      project_id: 'app_demo', boundary_state_fingerprint: 'f'.repeat(64),
      actors: [], actions: [], permissions: [], candidate_options: [],
    })
  })

  it('只把 Candidate 当识别依据，并要求用户填写真实业务结果', async () => {
    render(<BusinessBoundaryPage project={project} onError={vi.fn()} onStateChanged={vi.fn()} onBack={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: '从当前源码整理业务边界' })).toBeInTheDocument()
    expect(screen.getAllByText('项目负责人').length).toBeGreaterThan(0)
    expect(screen.queryByText(`role_${'1'.repeat(32)}`)).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText('例如：完整项目交付包真实形成')).toHaveValue('')
    expect(screen.queryByText(/创建任务|消息入队|Worker 执行/)).not.toBeInTheDocument()
  })

  it('待审 Proposal 不可编辑，返回修改后进入新本地草稿', async () => {
    mockApi.proposals.mockResolvedValue({ project_id: 'app_demo', proposals: [{ proposal, decision: null }] })
    render(<BusinessBoundaryPage project={project} onError={vi.fn()} onStateChanged={vi.fn()} onBack={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: '待确认业务边界' })).toBeInTheDocument()
    expect(screen.queryByLabelText('业务主体名称')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '返回修改' }))
    expect(await screen.findAllByLabelText('业务主体名称')).toHaveLength(2)
    expect(mockApi.createProposal).not.toHaveBeenCalled()
  })

  it('普通项目不读取或展示官方公开合同入口', async () => {
    render(<BusinessBoundaryPage project={project} onError={vi.fn()} onStateChanged={vi.fn()} onBack={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: '从当前源码整理业务边界' })).toBeInTheDocument()
    expect(screen.queryByText('官方公开合同')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '应用公开合同' })).not.toBeInTheDocument()
  })

  it('分别说明 revision 失效与从未确认当前权限', async () => {
    const current = {
      ...approvedBoundary,
      permission_intents: [],
      permission_statuses: [
        { ...approvedBoundary.permission_statuses[0], permission_semantics_confirmed: false, active_permission_count: 0, stale_permission_count: 1, allow_control_available: false, reason_codes: ['PERMISSION_REVISION_REVIEW_REQUIRED', 'ALLOW_CONTROL_REQUIRED', 'VALIDATION_PIPELINE_DEFERRED_TO_1_1_3'] },
        { ...approvedBoundary.permission_statuses[1], permission_semantics_confirmed: false, active_permission_count: 0, stale_permission_count: 0, allow_control_available: false, reason_codes: ['PERMISSION_SEMANTICS_REQUIRED', 'ALLOW_CONTROL_REQUIRED', 'VALIDATION_PIPELINE_DEFERRED_TO_1_1_3'] },
      ],
    }
    mockApi.current.mockResolvedValue(current)

    render(<BusinessBoundaryPage project={project} onError={vi.fn()} onStateChanged={vi.fn()} onBack={vi.fn()} />)
    expect(await screen.findByText('这项业务动作已经形成新 revision，原权限仍保留为历史，但当前 revision 需要重新确认权限。')).toBeInTheDocument()
    expect(screen.getByText('这项业务动作还没有当前权限规则。')).toBeInTheDocument()
    expect(screen.getByText('当前权限需要确认')).toBeInTheDocument()
  })

  it('只有拒绝规则时仍区分已确认语义与缺少允许对照', async () => {
    const current = {
      ...approvedBoundary,
      permission_statuses: approvedBoundary.permission_statuses.map((item: any) => ({
        ...item,
        allow_control_available: false,
        reason_codes: ['ALLOW_CONTROL_REQUIRED', 'VALIDATION_PIPELINE_DEFERRED_TO_1_1_3'],
      })),
    }
    mockApi.current.mockResolvedValue(current)

    render(<BusinessBoundaryPage project={project} onError={vi.fn()} onStateChanged={vi.fn()} onBack={vi.fn()} />)
    expect((await screen.findAllByText('权限语义已确认，验证合同暂不完整')).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/缺少覆盖同一业务结果的允许对照/).length).toBeGreaterThan(0)
    expect(screen.queryByText('当前权限尚未确认')).not.toBeInTheDocument()
  })

  it('已有正式边界时进入维护编辑器并提交 desired state', async () => {
    mockApi.current.mockResolvedValue(approvedBoundary)
    mockApi.maintenanceDraft.mockResolvedValue({
      project_id: 'app_demo', boundary_state_fingerprint: 'f'.repeat(64),
      actors: [{ item_id: 'pactr_existing', actor_id: approvedBoundary.actors[0].actor_id, expected_current_revision: 1, display_name: '项目负责人', description: '负责项目交付', effective_state: 'ACTIVE', source_candidate_ids: [] }],
      actions: [{ item_id: 'pactn_existing', action_id: approvedBoundary.actions[0].action_id, expected_current_revision: 1, display_name: '导出完整项目交付包', description: '形成交付包', primary_resource_concept: '项目交付空间', operation_kind: 'EXPORT', state_changing: true, effects: [{ item_id: 'peff_existing', effect_id: approvedBoundary.actions[0].effect_catalog[0].effect_id, business_label: '完整项目交付包真实形成', effect_kind: 'OBJECT_CREATION', resource_concept: '项目交付包', expected_state: null, protected_projection: [], description: '交付包已经形成' }], effective_state: 'ACTIVE', source_candidate_ids: [] }],
      permissions: [{ item_id: 'pperm_existing', intent_id: `pin_${'7'.repeat(32)}`, expected_current_revision: 1, effective_state: 'ACTIVE', subject_actor_item_id: 'pactr_existing', business_action_item_id: 'pactn_existing', resource_owner_actor_item_id: 'pactr_existing', relation: 'OWNS', expectation: 'ALLOW', protected_effect_item_ids: ['peff_existing'] }],
      candidate_options: [], implementation_inspections: [],
    })
    mockApi.createMaintenanceProposal.mockReturnValue(new Promise(() => {}))

    render(<BusinessBoundaryPage project={project} onError={vi.fn()} onStateChanged={vi.fn()} onBack={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '调整当前业务边界' }))
    expect(await screen.findByRole('heading', { name: '调整当前业务边界' })).toBeInTheDocument()
    expect(screen.queryByText(/write_mode/i)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '生成待审调整提案' }))

    await waitFor(() => expect(mockApi.createMaintenanceProposal).toHaveBeenCalledOnce())
    expect(JSON.stringify(mockApi.createMaintenanceProposal.mock.calls[0][1])).not.toContain('write_mode')
  })

  it('待审维护提案展示服务端生成的变更摘要', async () => {
    mockApi.proposals.mockResolvedValue({ project_id: 'app_demo', proposals: [{
      proposal, decision: null,
      change_summary: {
        new_actor_count: 1, new_action_count: 0,
        business_revision_updates: ['导出完整项目交付包'], retirements: [],
        permission_updates: [], permission_carry_forwards: ['负责人允许导出'], permission_retirements: [],
        implementation_rebinds: ['导出完整项目交付包'], unresolved_count: 0,
        change_codes: ['BUSINESS_REVISION_APPENDED', 'IMPLEMENTATION_REBOUND'],
      },
    }] })

    render(<BusinessBoundaryPage project={project} onError={vi.fn()} onStateChanged={vi.fn()} onBack={vi.fn()} />)

    expect(await screen.findByText('新增 1 个业务主体')).toBeInTheDocument()
    expect(screen.getByText('导出完整项目交付包 → 新 revision')).toBeInTheDocument()
    expect(screen.getByText('负责人允许导出 → 沿用到新 revision')).toBeInTheDocument()
    expect(screen.getByText('导出完整项目交付包 → 重新绑定到当前源码证据')).toBeInTheDocument()
  })
})
