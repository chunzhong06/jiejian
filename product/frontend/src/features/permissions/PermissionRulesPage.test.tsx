import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PermissionRulesPage } from './PermissionRulesPage'

const permissionApi = vi.hoisted(() => ({ profiles: vi.fn(), contract: vi.fn() }))
const contractsApi = vi.hoisted(() => ({ contracts: vi.fn(), contractGovernance: vi.fn(), createGovernanceContract: vi.fn(), transitionGovernanceVersion: vi.fn() }))
vi.mock('../../api/executionProfiles', () => ({ executionProfilesApi: permissionApi }))
vi.mock('../../api/contracts', () => ({ contractsApi }))

const contract = {
  contract_id: 'access', version: 1, status: 'ACTIVE', role_ids: ['admin'], workflow_states: ['OPEN'],
  subjects: [{ subject_id: 'alice', roles: ['admin'] }], actions: [{ action_id: 'read' }],
  resources: [{ resource_id: 'doc-1', resource_type: 'document', workflow_state: 'OPEN' }],
  relations: [{ relation_id: 'owns', relation: 'OWNS', source: { endpoint_type: 'subject', endpoint_id: 'alice' }, target: { endpoint_type: 'resource', endpoint_id: 'doc-1' } }],
  rules: [{ rule_id: 'allow-read', subject_id: 'alice', action_id: 'read', resource_id: 'doc-1', relation_path: ['owns'], context: {}, expectation: 'ALLOW', required_observations: ['resource_state'], coverage_dimensions: ['ROLE'], severity: 'high' }],
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
    const cell = await screen.findByRole('button', { name: /read doc-1/ })
    expect(cell).toHaveTextContent('允许')
    fireEvent.click(cell)
    fireEvent.click(await screen.findByText('高级：规则标识'))
    expect(await screen.findByText('allow-read')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: '关系图' }))
    expect(screen.getByRole('img', { name: /权限关系图 展示/ })).toBeInTheDocument()
    expect(screen.getByText(/alice — OWNS → doc-1/)).toBeInTheDocument()
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
    render(<PermissionRulesPage project={{ project_id: 'p1' }} onError={vi.fn()} />)

    fireEvent.change(await screen.findByLabelText('PermissionContract JSON 文件'), { target: { files: [file] } })
    expect(await screen.findByText('已选择：contract.json')).toBeInTheDocument()
    expect(screen.getByText('contract_id').parentElement).toHaveTextContent('access')
    fireEvent.click(screen.getByRole('button', { name: '创建草稿' }))

    await waitFor(() => expect(contractsApi.createGovernanceContract).toHaveBeenCalledWith('p1', contract, [], 'local-user'))
    expect(contractsApi.transitionGovernanceVersion).not.toHaveBeenCalled()
  })
})
