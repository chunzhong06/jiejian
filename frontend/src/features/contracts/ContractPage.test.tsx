import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ContractPage from './ContractPage'

const mockApi = vi.hoisted(() => ({
  contractGovernance: vi.fn(),
  contracts: vi.fn(),
  createRequirement: vi.fn(),
  deriveCandidates: vi.fn(),
  llmCandidates: vi.fn(),
  createGovernanceContract: vi.fn(),
  reviseGovernanceContract: vi.fn(),
  transitionGovernanceVersion: vi.fn(),
  assessment: vi.fn(),
  diff: vi.fn(),
  drift: vi.fn(),
  activateContract: vi.fn(),
}))

vi.mock('../../api/contracts', () => ({ contractsApi: mockApi }))
vi.mock('../../api/http', () => ({ ApiError: class extends Error {} }))

const snapshot = () => ({
  project: { project_id: 'p1', governed_contract_id: null, governed_contract_version: null },
  requirements: [{ requirement_id: 'req-1', text: '受控需求' }],
  candidates: [{ candidate_id: 'cand-1', rule: { id: 'rule-1' }, source: { source_type: 'requirement_text' } }],
  versions: [{ contract_id: 'c1', version: 1, status: 'DRAFT', snapshot: { rules: [{ id: 'rule-1' }] } }],
  flow_merge: { candidates: [], issues: [] },
  llm_available: false,
})

const projectSnapshot = (project: Record<string, unknown>, versions = snapshot().versions) => ({
  ...snapshot(),
  project,
  versions,
})

describe('ContractPage', () => {
  beforeEach(() => {
    cleanup()
    mockApi.contractGovernance.mockResolvedValue(snapshot())
    mockApi.contracts.mockResolvedValue([{ id: 'yaml-contract', version: 1, status: 'ACTIVE', path: 'contract.yaml' }])
    mockApi.createRequirement.mockResolvedValue({})
    mockApi.activateContract.mockResolvedValue({})
    mockApi.deriveCandidates.mockResolvedValue({ batches: [{ issues: [{ severity: 'BLOCKING', code: 'AMBIGUOUS_SOURCE' }] }], merge: { issues: [] }, persisted_candidates: [] })
    mockApi.transitionGovernanceVersion.mockResolvedValue({})
    vi.clearAllMocks()
    mockApi.contractGovernance.mockResolvedValue(snapshot())
    mockApi.contracts.mockResolvedValue([{ id: 'yaml-contract', version: 1, status: 'ACTIVE', path: 'contract.yaml' }])
  })

  it('恢复工作台、显示离线 LLM、阻断派生并展示稳定 issue code', async () => {
    render(<ContractPage project={{ project_id: 'p1' }} profiles={[]} onError={vi.fn()} />)
    expect(await screen.findByText('LLM 离线')).toBeInTheDocument()
    expect(screen.getByText('兼容：显式 Contract 文件')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '派生候选' })).toBeDisabled()
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    fireEvent.click(screen.getByRole('checkbox', { name: '包含当前已校验 Flow（可独立派生）' }))
    fireEvent.click(screen.getByRole('button', { name: '派生候选' }))
    await waitFor(() => expect(mockApi.deriveCandidates).toHaveBeenCalledWith('p1', ['req-1'], true, 'local-user'))
    expect(await screen.findByText('存在阻断问题，本批候选未落盘')).toBeInTheDocument()
    expect(screen.getByText(/AMBIGUOUS_SOURCE/)).toBeInTheDocument()
  })

  it('新增 Requirement 传递正文、标签和可见 actor', async () => {
    render(<ContractPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    await screen.findByText('LLM 离线')
    fireEvent.change(screen.getByPlaceholderText('rule id=foreign-read kind=foreign_read observers=http severity=high'), { target: { value: 'rule id=added kind=foreign_read observers=http severity=high' } })
    fireEvent.change(screen.getByPlaceholderText('标签，用逗号分隔'), { target: { value: 'pii, auth' } })
    fireEvent.change(screen.getByPlaceholderText('actor'), { target: { value: 'reviewer-1' } })
    fireEvent.click(screen.getByRole('button', { name: '新增 Requirement' }))
    await waitFor(() => expect(mockApi.createRequirement).toHaveBeenCalledWith('p1', 'rule id=added kind=foreign_read observers=http severity=high', ['pii', 'auth'], 'reviewer-1'))
    await waitFor(() => expect(mockApi.contractGovernance.mock.calls.length).toBeGreaterThan(1))
  })

  it('激活 YAML 兼容入口并刷新工作台', async () => {
    render(<ContractPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    await screen.findByText('兼容：显式 Contract 文件')
    fireEvent.change(screen.getByPlaceholderText(/demo.*contract\.yaml/), { target: { value: 'D:\\demo\\contract.yaml' } })
    fireEvent.click(screen.getByRole('button', { name: '激活 YAML' }))
    await waitFor(() => expect(mockApi.activateContract).toHaveBeenCalledWith('p1', 'D:\\demo\\contract.yaml'))
    await waitFor(() => expect(mockApi.contractGovernance.mock.calls.length).toBeGreaterThan(1))
  })

  it('按选定候选创建草稿、提交审阅并刷新', async () => {
    render(<ContractPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    await screen.findByText('c1 v1 · DRAFT')
    fireEvent.change(screen.getAllByPlaceholderText('contract_id')[0], { target: { value: 'c1' } })
    fireEvent.click(screen.getAllByRole('checkbox')[2])
    fireEvent.click(screen.getAllByRole('button', { name: '创建 DRAFT' })[0])
    await waitFor(() => expect(mockApi.createGovernanceContract).toHaveBeenCalledWith('p1', 'c1', ['cand-1'], 'local-user'))
    fireEvent.click(screen.getAllByRole('button', { name: '提交审阅' })[0])
    await waitFor(() => expect(mockApi.transitionGovernanceVersion).toHaveBeenCalledWith('p1', 'c1', 1, 'submit', 'local-user'))
    await waitFor(() => expect(mockApi.contractGovernance.mock.calls.length).toBeGreaterThan(1))
  })

  it('在 REVIEW 状态显示并执行激活动作', async () => {
    mockApi.contractGovernance.mockResolvedValue({ ...snapshot(), versions: [{ ...snapshot().versions[0], status: 'REVIEW' }] })
    render(<ContractPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    await screen.findByText('c1 v1 · REVIEW')
    fireEvent.click(screen.getByRole('button', { name: /^激\s*活$/ }))
    await waitFor(() => expect(mockApi.transitionGovernanceVersion).toHaveBeenCalledWith('p1', 'c1', 1, 'activate', 'local-user'))
    await waitFor(() => expect(mockApi.contractGovernance.mock.calls.length).toBeGreaterThan(1))
  })

  it('修订绑定的 ACTIVE Contract，而非其他 ACTIVE 版本', async () => {
    const versions = [
      { contract_id: 'c1', version: 1, status: 'ACTIVE', snapshot: { rules: [{ id: 'rule-1' }] } },
      { contract_id: 'c2', version: 3, status: 'ACTIVE', snapshot: { rules: [{ id: 'rule-2' }] } },
    ]
    mockApi.contractGovernance.mockResolvedValue(projectSnapshot({ project_id: 'p1', governed_contract_id: 'c2', governed_contract_version: 3 }, versions))
    render(<ContractPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    await screen.findByText('c2 v3 · ACTIVE')
    expect(screen.getByPlaceholderText('contract_id')).toHaveValue('c2')
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[checkboxes.length - 1])
    fireEvent.click(screen.getByRole('button', { name: '修订 ACTIVE' }))
    await waitFor(() => expect(mockApi.reviseGovernanceContract).toHaveBeenCalledWith('p1', 'c2', ['cand-1'], 'local-user'))
  })

  it('项目切换时清空旧项目的选择', async () => {
    const { rerender } = render(<ContractPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    await screen.findByText('c1 v1 · DRAFT')
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    mockApi.contractGovernance.mockResolvedValue(projectSnapshot({ project_id: 'p2', governed_contract_id: null, governed_contract_version: null }))
    rerender(<ContractPage project={{ project_id: 'p2' }} onError={vi.fn()} />)
    await screen.findByText('p2')
    expect(screen.getByRole('button', { name: '派生候选' })).toBeDisabled()
  })

  it('选择已配置 Profile 后显式生成 LLM Candidate', async () => {
    mockApi.llmCandidates.mockResolvedValue({ candidates: [], input_sha256: 'a'.repeat(64), output_sha256: 'b'.repeat(64) })
    const profile = {
      schema_version: '1' as const, profile_name: 'profile-1', provider: 'openai' as const, model: 'gpt-test',
      base_url: null, timeout_ms: 30000, max_input_bytes: 131072, max_output_bytes: 65536,
      max_budget_microusd: 1000000, enabled: true, secret_ref: 'env:KEY', allow_local_http: false,
      created_at_us: 1, updated_at_us: 1, secret_configured: true, connection_status: 'configured' as const,
      tested_at_us: null, duration_ms: null, error_code: null, error_message: null,
    }
    render(<ContractPage project={{ project_id: 'p1' }} profiles={[profile]} onError={vi.fn()} />)
    await screen.findByText('LLM 可用')
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'LLM profile' }))
    fireEvent.click(await screen.findByText('profile-1 · openai'))
    fireEvent.click(screen.getByRole('button', { name: '生成 LLM 候选' }))
    await waitFor(() => expect(mockApi.llmCandidates).toHaveBeenCalledWith('p1', ['req-1'], 'local-user', 'profile-1'))
  })
})
