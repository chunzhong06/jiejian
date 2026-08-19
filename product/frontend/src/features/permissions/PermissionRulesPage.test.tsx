import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PermissionRulesPage } from './PermissionRulesPage'

const permissionApi = vi.hoisted(() => ({ profiles: vi.fn(), contract: vi.fn() }))
const contractsApi = vi.hoisted(() => ({ contracts: vi.fn(), contractGovernance: vi.fn(), createGovernanceContract: vi.fn(), transitionGovernanceVersion: vi.fn() }))
vi.mock('../../api/executionProfiles', () => ({ executionProfilesApi: permissionApi }))
vi.mock('../../api/contracts', () => ({ contractsApi }))

const contract = {
  contract_id: 'access', version: 1, status: 'ACTIVE', role_ids: ['admin', 'member'], workflow_states: ['OPEN'],
  subjects: [{ subject_id: 'alice', roles: ['admin'] }, { subject_id: 'bob', roles: ['member'] }], actions: [{ action_id: 'read' }, { action_id: 'write' }],
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
  it('展示真实矩阵、规则详情和关系文本等价视图', async () => {
    permissionApi.profiles.mockResolvedValue([{ profile_id: 'profile-1', contract_id: 'access', contract_version: 1 }])
    permissionApi.contract.mockResolvedValue(contract)
    contractsApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [], llm_available: false })
    contractsApi.contracts.mockResolvedValue([])
    render(<PermissionRulesPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    expect(await screen.findByText(/alice/)).toBeInTheDocument()
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
    expect(within(graph).getAllByRole('button').length).toBeGreaterThanOrEqual(3)
    expect(screen.getByText(/alice — OWNS → doc-1/)).toBeInTheDocument()
    fireEvent.click(await screen.findByLabelText('身份 alice'))
    expect(await screen.findByText('正在聚焦：alice')).toBeInTheDocument()
    expect(screen.getByText('当前身份的权限')).toBeInTheDocument()
  })

  it('没有已登记 Profile 时展示当前激活契约摘要并说明关系视图不可用', async () => {
    permissionApi.profiles.mockResolvedValue([])
    contractsApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [], llm_available: false })
    contractsApi.contracts.mockResolvedValue([{ id: 'governed', version: 1, status: 'ACTIVE', rules: [{ id: 'governed-rule', expectation: 'ALLOW' }] }])
    render(<PermissionRulesPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('governed-rule')).toBeInTheDocument())
    expect(screen.getByText('当前治理摘要只返回规则字段，不包含身份、动作、资源和关系实体，因此关系视图不可用。')).toBeInTheDocument()
  })

  it('选择 PermissionContract 后创建草稿只提交完整快照，不自动提交或激活', async () => {
    permissionApi.profiles.mockResolvedValue([])
    contractsApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [], llm_available: false })
    contractsApi.contracts.mockResolvedValue([])
    contractsApi.createGovernanceContract.mockResolvedValue({ contract_id: 'access', version: 1, status: 'DRAFT' })
    const file = new File([JSON.stringify(contract)], 'contract.json', { type: 'application/json' })
    Object.defineProperty(file, 'text', { value: vi.fn().mockResolvedValue(JSON.stringify(contract)) })
    render(<PermissionRulesPage project={{ project_id: 'p1' }} onError={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /高级：规则治理与当前配置/ }))
    fireEvent.change(await screen.findByLabelText('PermissionContract JSON 文件'), { target: { files: [file] } })
    expect(await screen.findByText('已选择：contract.json')).toBeInTheDocument()
    expect((await screen.findByText('contract_id')).parentElement).toHaveTextContent('access')
    fireEvent.click(screen.getByRole('button', { name: '创建草稿' }))

    await waitFor(() => expect(contractsApi.createGovernanceContract).toHaveBeenCalledWith('p1', contract, [], 'local-user'))
    expect(contractsApi.transitionGovernanceVersion).not.toHaveBeenCalled()
  })
})
