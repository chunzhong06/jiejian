// 验证高级权限工具只在展开后浏览生成配置，并把治理变化通知普通检查状态机。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PermissionAdvancedPanel } from './PermissionAdvancedPanel'

const profilesApi = vi.hoisted(() => ({ profiles: vi.fn(), contract: vi.fn(), summary: vi.fn() }))
const contractsApi = vi.hoisted(() => ({
  contracts: vi.fn(), contractGovernance: vi.fn(), createGovernanceContract: vi.fn(), transitionGovernanceVersion: vi.fn(),
}))
vi.mock('../../api/executionProfiles', () => ({ executionProfilesApi: profilesApi }))
vi.mock('../../api/contracts', () => ({ contractsApi }))

const contract = {
  contract_id: 'access', version: 1, status: 'ACTIVE', role_ids: ['member'], workflow_states: ['OPEN'],
  subjects: [{ subject_id: 'alice', roles: ['member'] }],
  effects: [{ effect_id: 'document-change', kind: 'STATE_MUTATION', resource_type: 'document' }],
  actions: [{ action_id: 'modify', effect_ids: ['document-change'] }],
  resources: [{ resource_id: 'doc-1', resource_type: 'document', workflow_state: 'OPEN' }],
  relations: [{ relation_id: 'owns', relation: 'OWNS', source: { endpoint_type: 'subject', endpoint_id: 'alice' }, target: { endpoint_type: 'resource', endpoint_id: 'doc-1' } }],
  rules: [{ rule_id: 'allow-modify', subject_id: 'alice', action_id: 'modify', resource_id: 'doc-1', relation_path: ['owns'], context: {}, expectation: 'ALLOW', required_observations: ['resource_state'], coverage_dimensions: ['ROLE'], severity: 'high' }],
  batch_rules: [],
}

describe('PermissionAdvancedPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    profilesApi.profiles.mockResolvedValue([])
    profilesApi.summary.mockResolvedValue({ schema_version: '1', workflows: [], effect_bindings: [] })
    contractsApi.contracts.mockResolvedValue([])
    contractsApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [] })
  })

  it('展开后展示生成配置、业务流程、真实影响和关系视图', async () => {
    profilesApi.profiles.mockResolvedValue([{ profile_id: 'profile-1', contract_id: 'access', contract_version: 1 }])
    profilesApi.contract.mockResolvedValue(contract)
    profilesApi.summary.mockResolvedValue({
      schema_version: '1',
      workflows: [{ action_id: 'modify', workflow_id: 'modify-flow', target_step: { step_id: 'target', method: 'PATCH', path: '/documents/{id}' }, setup_step_count: 1, cleanup_step_count: 1, baseline_modes: ['EXACT_RESTORE'] }],
      effect_bindings: [{ effect_id: 'document-change', required_channels: ['resource_state'], corroborating_channels: [], closure_policy: 'IMMEDIATE' }],
    })
    render(<PermissionAdvancedPanel project={{ project_id: 'p1' }} onError={vi.fn()} onAuthorityChanged={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /高级：生成配置与规则详情/ }))
    expect(await screen.findByText('业务流程与真实影响')).toBeInTheDocument()
    expect(screen.getByText('恢复同一资源')).toBeInTheDocument()
    expect(screen.getByText('状态变更')).toBeInTheDocument()
    expect(screen.getByText('即时闭合')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /alice modify doc-1 允许/ })).toBeInTheDocument()
  })

  it('高级治理创建草稿后通知普通页面失效旧 preview，但不自动激活规则', async () => {
    contractsApi.createGovernanceContract.mockResolvedValue({ contract_id: 'access', version: 1, status: 'DRAFT' })
    const onAuthorityChanged = vi.fn()
    const file = new File([JSON.stringify(contract)], 'contract.json', { type: 'application/json' })
    Object.defineProperty(file, 'text', { value: vi.fn().mockResolvedValue(JSON.stringify(contract)) })
    render(<PermissionAdvancedPanel project={{ project_id: 'p1' }} onError={vi.fn()} onAuthorityChanged={onAuthorityChanged} />)

    fireEvent.click(screen.getByRole('button', { name: /高级：规则治理与手工配置/ }))
    fireEvent.change(await screen.findByLabelText('权限契约 JSON 文件'), { target: { files: [file] } })
    expect(await screen.findByText('已选择：contract.json')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '创建草稿' }))

    await waitFor(() => expect(contractsApi.createGovernanceContract).toHaveBeenCalledWith('p1', contract, [], 'local-user'))
    await waitFor(() => expect(onAuthorityChanged).toHaveBeenCalledOnce())
    expect(contractsApi.transitionGovernanceVersion).not.toHaveBeenCalled()
  })

  it('没有执行配置时保留已激活治理规则摘要并说明关系视图边界', async () => {
    contractsApi.contracts.mockResolvedValue([{ id: 'governed', version: 1, status: 'ACTIVE', rules: [{ id: 'governed-rule', expectation: 'ALLOW' }] }])
    render(<PermissionAdvancedPanel project={{ project_id: 'p1' }} onError={vi.fn()} onAuthorityChanged={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /高级：生成配置与规则详情/ }))
    expect(await screen.findByText('governed-rule')).toBeInTheDocument()
    expect(screen.getByText('当前治理摘要只返回规则字段，不包含身份、动作、资源和关系实体，因此关系视图不可用。')).toBeInTheDocument()
  })
})
