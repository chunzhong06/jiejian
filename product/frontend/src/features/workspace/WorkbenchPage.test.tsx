import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { WorkbenchPage } from './WorkbenchPage'

const contractsApi = vi.hoisted(() => ({ contracts: vi.fn(), contractGovernance: vi.fn() }))
vi.mock('../../api/contracts', () => ({ contractsApi }))

describe('WorkbenchPage', () => {
  it('只按当前绑定的有效规则快照计算规则数量，并展示最近检查结论', async () => {
    contractsApi.contracts.mockResolvedValue([{ id: 'governed', rules: [{ id: 'governed-rule' }] }])
    contractsApi.contractGovernance.mockResolvedValue({
      project: { governed_contract_id: 'c2', governed_contract_version: 3 },
      versions: [
        { contract_id: 'c1', version: 1, status: 'ACTIVE', snapshot: { rules: [{ id: 'other-1' }, { id: 'other-2' }] } },
        { contract_id: 'c2', version: 3, status: 'ACTIVE', snapshot: { rules: [{ id: 'bound-1' }, { id: 'bound-2' }, { id: 'bound-3' }] } },
      ],
    })
    render(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用', status: 'INTERNAL_STATE' }} runs={[{ lifecycle: 'COMPLETED', verdict: 'INCONCLUSIVE', result_integrity: 'VERIFIED' }]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} profiles={[]} llmLoadFailed={false} onNavigate={vi.fn()} onError={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument())
    expect(screen.getAllByText('已选择').length).toBeGreaterThan(0)
    expect(screen.queryByText('INTERNAL_STATE')).not.toBeInTheDocument()
    expect(screen.getByText('证据不足，暂时不能下结论')).toBeInTheDocument()
    expect(screen.getByText('结果完整')).toBeInTheDocument()
    expect(screen.queryByText('2')).not.toBeInTheDocument()
  })

  it('没有应用时给出应用接入主操作', () => {
    const onNavigate = vi.fn()
    render(<WorkbenchPage selected={null} runs={[]} systemStatus={{ api: 'unknown', worker: 'unknown', browser: 'unknown' }} profiles={[]} llmLoadFailed={false} onNavigate={onNavigate} onError={vi.fn()} />)
    expect(screen.getByText('还没有选择要检查的应用。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '选择应用' })).toBeInTheDocument()
  })
})
