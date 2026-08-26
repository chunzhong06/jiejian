// 验证普通权限意图矩阵与高级 Contract/Profile 浏览入口保持职责分离。

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PermissionRulesPage } from './PermissionRulesPage'

const permissionApi = vi.hoisted(() => ({ profiles: vi.fn(), contract: vi.fn(), summary: vi.fn() }))
const contractsApi = vi.hoisted(() => ({ contracts: vi.fn(), contractGovernance: vi.fn(), createGovernanceContract: vi.fn(), transitionGovernanceVersion: vi.fn() }))
const intentApi = vi.hoisted(() => ({ matrix: vi.fn(), confirm: vi.fn(), compile: vi.fn() }))
const projectsApi = vi.hoisted(() => ({ readiness: vi.fn() }))
vi.mock('../../api/executionProfiles', () => ({ executionProfilesApi: permissionApi }))
vi.mock('../../api/contracts', () => ({ contractsApi }))
vi.mock('../../api/permissionIntents', () => ({ permissionIntentsApi: intentApi }))
vi.mock('../../api/projects', () => ({ projectsApi }))

const contract = {
  contract_id: 'access', version: 1, status: 'ACTIVE', role_ids: ['admin', 'member'], workflow_states: ['OPEN'],
  subjects: [{ subject_id: 'alice', roles: ['admin'] }, { subject_id: 'bob', roles: ['member'] }],
  effects: [{ effect_id: 'document-change', kind: 'STATE_MUTATION', resource_type: 'document' }],
  actions: [{ action_id: 'read', effect_ids: ['document-change'] }, { action_id: 'write', effect_ids: ['document-change'] }],
  resources: [{ resource_id: 'doc-1', resource_type: 'document', workflow_state: 'OPEN' }, { resource_id: 'doc-2', resource_type: 'document', workflow_state: 'OPEN' }],
  relations: [{ relation_id: 'owns', relation: 'OWNS', source: { endpoint_type: 'subject', endpoint_id: 'alice' }, target: { endpoint_type: 'resource', endpoint_id: 'doc-1' } }],
  rules: [
    { rule_id: 'allow-read', subject_id: 'alice', action_id: 'read', resource_id: 'doc-1', relation_path: ['owns'], context: {}, expectation: 'ALLOW', required_observations: ['resource_state'], coverage_dimensions: ['ROLE'], severity: 'high' },
    { rule_id: 'deny-write', subject_id: 'bob', action_id: 'write', resource_id: 'doc-1', relation_path: [], context: {}, expectation: 'DENY', required_observations: ['resource_state'], coverage_dimensions: ['ROLE'], severity: 'critical' },
    { rule_id: 'conflict-allow', subject_id: 'alice', action_id: 'write', resource_id: 'doc-2', relation_path: [], context: {}, expectation: 'ALLOW', required_observations: [], coverage_dimensions: [], severity: 'medium' },
    { rule_id: 'conflict-deny', subject_id: 'alice', action_id: 'write', resource_id: 'doc-2', relation_path: [], context: {}, expectation: 'DENY', required_observations: [], coverage_dimensions: [], severity: 'medium' },
  ],
  batch_rules: [],
}

describe('PermissionRulesPage', () => {
  beforeEach(() => {
    intentApi.matrix.mockResolvedValue({ project_id: 'p1', actions: [], confirmed_count: 0, review_required_count: 0, unconfirmed_count: 0, compilable_action_count: 0 })
    projectsApi.readiness.mockResolvedValue({ project_id: 'p1', current_scope_runnable: false, remaining_gap_count: 1 })
    permissionApi.summary.mockResolvedValue({
      schema_version: '1',
      workflows: [{ action_id: 'read', workflow_id: 'read-flow', target_step: { step_id: 'target', method: 'GET', path: '/documents/{id}' }, setup_step_count: 1, cleanup_step_count: 1, baseline_modes: ['EXACT_RESTORE'] }],
      effect_bindings: [{ effect_id: 'document-change', required_channels: ['resource_state'], corroborating_channels: [], closure_policy: 'IMMEDIATE' }],
    })
  })

  it('展示真实矩阵、规则详情和关系文本等价视图', async () => {
    permissionApi.profiles.mockResolvedValue([{ profile_id: 'profile-1', contract_id: 'access', contract_version: 1 }])
    permissionApi.contract.mockResolvedValue(contract)
    contractsApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [] })
    contractsApi.contracts.mockResolvedValue([])
    render(<PermissionRulesPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /高级：生成配置与规则详情/ }))
    expect(await screen.findByText('业务流程与真实影响')).toBeInTheDocument()
    expect(screen.getByText('恢复同一资源')).toBeInTheDocument()
    expect(screen.getByText('状态变更')).toBeInTheDocument()
    expect(screen.getByText('即时闭合')).toBeInTheDocument()
    expect((await screen.findAllByText('alice')).length).toBeGreaterThanOrEqual(1)
    const cell = await screen.findByRole('button', { name: /alice read doc-1 允许/ })
    expect(cell).toHaveTextContent('允许')
    expect(screen.getByRole('button', { name: /alice read doc-2 未声明/ })).toHaveTextContent('未声明')
    expect(screen.getByRole('button', { name: /alice write doc-2 规则冲突/ })).toHaveTextContent('规则冲突')
    expect(screen.getByRole('button', { name: /bob write doc-1 拒绝/ })).toHaveTextContent('拒绝')
    expect(screen.getByRole('combobox', { name: '筛选身份' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '筛选角色' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '筛选动作' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '筛选资源' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: /alice read doc-1 允许/ }))
    fireEvent.click(await screen.findByText('高级：规则标识'))
    expect(await screen.findByText('allow-read')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: '关系图' }))
    const graph = await screen.findByRole('region', { name: '权限关系图' })
    expect(within(graph).getAllByRole('button')).toHaveLength(2)
    expect(graph.querySelector('.react-flow')).not.toBeInTheDocument()
    expect(screen.getAllByText('拥有').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('doc-1').length).toBeGreaterThanOrEqual(1)
    fireEvent.click(await screen.findByLabelText('身份 alice'))
    expect(await screen.findByText('正在聚焦：alice')).toBeInTheDocument()
    expect(screen.getByText('当前身份的权限')).toBeInTheDocument()
  })

  it('没有已登记 Profile 时展示当前激活契约摘要并说明关系视图不可用', async () => {
    permissionApi.profiles.mockResolvedValue([])
    contractsApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [] })
    contractsApi.contracts.mockResolvedValue([{ id: 'governed', version: 1, status: 'ACTIVE', rules: [{ id: 'governed-rule', expectation: 'ALLOW' }] }])
    render(<PermissionRulesPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /高级：生成配置与规则详情/ }))
    await waitFor(() => expect(screen.getByText('governed-rule')).toBeInTheDocument())
    expect(screen.getByText('当前治理摘要只返回规则字段，不包含身份、动作、资源和关系实体，因此关系视图不可用。')).toBeInTheDocument()
  })

  it('内置示例使用中文业务含义并保留协议原值，规则版本列表占满可用宽度', async () => {
    const demoContract = {
      ...contract,
      subjects: [{ subject_id: 'attacker', roles: ['user'] }, { subject_id: 'owner', roles: ['user'] }],
      actions: [{ action_id: 'modify' }],
      resources: [
        { resource_id: 'attacker-resource', resource_type: 'document' },
        { resource_id: 'owner-resource', resource_type: 'document' },
      ],
      relations: [{ relation_id: 'attacker-owns', relation: 'OWNS', source: { endpoint_type: 'subject', endpoint_id: 'attacker' }, target: { endpoint_type: 'resource', endpoint_id: 'attacker-resource' } }],
      rules: [{ rule_id: 'unauthorized-modify', subject_id: 'attacker', action_id: 'modify', resource_id: 'owner-resource', expectation: 'DENY', severity: 'critical' }],
    }
    permissionApi.profiles.mockResolvedValue([{ profile_id: 'profile-1', contract_id: 'access', contract_version: 1 }])
    permissionApi.contract.mockResolvedValue(demoContract)
    contractsApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [{ contract_id: 'access', version: 1, status: 'ACTIVE', snapshot: demoContract }] })
    contractsApi.contracts.mockResolvedValue([])

    render(<PermissionRulesPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /高级：生成配置与规则详情/ }))

    expect((await screen.findAllByText('攻击者')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('attacker').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('修改').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('modify').length).toBeGreaterThanOrEqual(1)
    fireEvent.click(screen.getByRole('tab', { name: '关系图' }))
    expect((await screen.findAllByText('拥有')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('文档').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('attacker-resource').length).toBeGreaterThanOrEqual(1)
    expect(document.querySelector('.governance-version-list')).toBeInTheDocument()
    expect(document.querySelector('.governance-version-item')).toHaveTextContent('已激活')
  })

  it('选择 PermissionContract 后创建草稿只提交完整快照，不自动提交或激活', async () => {
    permissionApi.profiles.mockResolvedValue([])
    contractsApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [] })
    contractsApi.contracts.mockResolvedValue([])
    contractsApi.createGovernanceContract.mockResolvedValue({ contract_id: 'access', version: 1, status: 'DRAFT' })
    const file = new File([JSON.stringify(contract)], 'contract.json', { type: 'application/json' })
    Object.defineProperty(file, 'text', { value: vi.fn().mockResolvedValue(JSON.stringify(contract)) })
    render(<PermissionRulesPage project={{ project_id: 'p1' }} onError={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /高级：规则治理与手工配置/ }))
    fireEvent.change(await screen.findByLabelText('权限契约 JSON 文件'), { target: { files: [file] } })
    expect(await screen.findByText('已选择：contract.json')).toBeInTheDocument()
    expect((await screen.findByText('契约标识（contract_id）')).parentElement).toHaveTextContent('access')
    fireEvent.click(screen.getByRole('button', { name: '创建草稿' }))

    await waitFor(() => expect(contractsApi.createGovernanceContract).toHaveBeenCalledWith('p1', contract, [], 'local-user'))
    expect(contractsApi.transitionGovernanceVersion).not.toHaveBeenCalled()
  })

  it('普通页面用中文权限组与动作矩阵确认允许和拒绝，不要求编辑 JSON', async () => {
    const matrix = {
      project_id: 'p1', confirmed_count: 0, review_required_count: 0, unconfirmed_count: 2, executable_count: 0, representative_gap_count: 1, compilable_action_count: 1,
      actions: [{
        action_candidate_id: 'action_' + '1'.repeat(32), action_display_name: '修改测试文档', resource_logical_name: '所有者的测试文档', gaps: ['ALLOW_INTENT_MISSING', 'DENY_INTENT_MISSING'], required_intent_count: 2, confirmed_intent_count: 0, executable_intent_count: 0, representative_gap_count: 0, compilable: false,
        cells: [
          { action_candidate_id: 'action_' + '1'.repeat(32), subject_role_candidate_id: 'role_' + '4'.repeat(32), subject_role_display_name: '所有者', resource_owner_role_candidate_id: 'role_' + '4'.repeat(32), resource_owner_role_display_name: '所有者', relation: 'OWNS', expectation: null, status: 'UNCONFIRMED', review_reasons: ['PERMISSION_INTENT_UNCONFIRMED'], intent_fingerprint: null, representative_test_identity_id: 'tid_' + '3'.repeat(32), representative_label: '所有者账号', execution_gap: null },
          { action_candidate_id: 'action_' + '1'.repeat(32), subject_role_candidate_id: 'role_' + '4'.repeat(32), subject_role_display_name: '所有者', resource_owner_role_candidate_id: 'role_' + '4'.repeat(32), resource_owner_role_display_name: '所有者', relation: 'SAME_ROLE_OTHER_ACCOUNT', expectation: null, status: 'UNCONFIRMED', review_reasons: ['PERMISSION_INTENT_UNCONFIRMED'], intent_fingerprint: null, representative_test_identity_id: null, representative_label: null, execution_gap: 'TEST_IDENTITY_MISSING' },
        ],
      }],
    }
    intentApi.matrix.mockResolvedValue(matrix)
    intentApi.confirm.mockResolvedValue(matrix)
    projectsApi.readiness.mockResolvedValue({ project_id: 'p1', current_scope_runnable: true, remaining_gap_count: 0 })
    permissionApi.profiles.mockResolvedValue([])
    contractsApi.contracts.mockResolvedValue([])
    contractsApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [] })

    render(<PermissionRulesPage project={{ project_id: 'p1' }} onError={vi.fn()} onNext={vi.fn()} />)

    expect(await screen.findByText('业务动作：修改测试文档')).toBeInTheDocument()
    expect(screen.getByText('测试资源：所有者的测试文档')).toBeInTheDocument()
    expect(screen.getAllByText('资源所属权限组：所有者').length).toBeGreaterThan(0)
    expect(screen.getByText('所有者 · 自己的资源')).toBeInTheDocument()
    expect(screen.getByText(/同权限组其他用户的资源/)).toBeInTheDocument()
    const sameGroup = screen.getByLabelText('所有者权限组以同权限组其他用户的资源关系对修改测试文档的权限')
    expect(sameGroup).not.toBeDisabled()
    expect(screen.getByText('小提示：还需要第二个所有者测试账号才能实际检查这一项')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始检查' })).toBeInTheDocument()
    fireEvent.click(within(screen.getByLabelText('所有者权限组以自己的资源关系对修改测试文档的权限')).getByText('允许'))
    await waitFor(() => expect(intentApi.confirm).toHaveBeenCalledWith('p1', 'action_' + '1'.repeat(32), 'role_' + '4'.repeat(32), 'role_' + '4'.repeat(32), 'OWNS', 'ALLOW', 'local-user'))
    await waitFor(() => expect(screen.queryByRole('button', { name: '开始检查' })).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: '准备检查' })).toBeInTheDocument()
    expect(screen.getByText('界鉴会根据已确认权限组生成受控检查配置。')).toBeInTheDocument()
  })

  it('准备检查后只显示业务数量和测试条件缺口', async () => {
    const actionId = 'action_' + '6'.repeat(32)
    const matrix = {
      project_id: 'p1', confirmed_count: 2, review_required_count: 0, unconfirmed_count: 0, executable_count: 2, representative_gap_count: 0, compilable_action_count: 1,
      actions: [{
        action_candidate_id: actionId, action_display_name: '读取文档', resource_logical_name: '普通用户的测试文档', gaps: [], required_intent_count: 2, confirmed_intent_count: 2, executable_intent_count: 2, representative_gap_count: 0, compilable: true,
        cells: [{ action_candidate_id: actionId, subject_role_candidate_id: 'role_' + '7'.repeat(32), subject_role_display_name: '普通用户', resource_owner_role_candidate_id: 'role_' + '7'.repeat(32), resource_owner_role_display_name: '普通用户', relation: 'OWNS', expectation: 'ALLOW', status: 'CURRENT', review_reasons: [], intent_fingerprint: 'a'.repeat(64), representative_test_identity_id: 'tid_' + '8'.repeat(32), representative_label: '普通用户A', execution_gap: null }],
      }],
    }
    intentApi.matrix.mockResolvedValueOnce(matrix).mockResolvedValue({ ...matrix, representative_gap_count: 1 })
    intentApi.compile.mockResolvedValue({ covered_action_ids: [actionId] })
    projectsApi.readiness.mockResolvedValueOnce({ project_id: 'p1', current_scope_runnable: false, remaining_gap_count: 1 }).mockResolvedValue({ project_id: 'p1', current_scope_runnable: true, remaining_gap_count: 0 })
    permissionApi.profiles.mockResolvedValue([])
    contractsApi.contracts.mockResolvedValue([])
    contractsApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [] })

    const onResolved = vi.fn()
    render(<PermissionRulesPage project={{ project_id: 'p1' }} onError={vi.fn()} onResolved={onResolved} onNext={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '准备检查' }))
    await waitFor(() => expect(intentApi.compile).toHaveBeenCalledWith('p1', 'local-user'))
    expect(await screen.findByText('已准备 1 个业务动作；1 项权限要求暂缺测试条件。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始检查' })).toBeInTheDocument()
    expect(onResolved).toHaveBeenCalledOnce()
    expect(screen.queryByText(/Profile ID|Contract ID|profile_id|contract_id/i)).not.toBeInTheDocument()
  })
})
