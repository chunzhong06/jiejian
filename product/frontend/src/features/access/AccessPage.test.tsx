import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AccessPage } from './AccessPage'

describe('AccessPage', () => {
  it('按真实更新时间排序，并只展示真实当前项目概览', () => {
    render(
      <AccessPage
        projects={[
          { project_id: 'old', name: '旧项目', status: 'REGISTERED', updated_at_us: 1 },
          { project_id: 'new', name: '新项目', status: 'READY', updated_at_us: 2, governed_contract_id: 'contract-1', governed_contract_version: 3 },
        ]}
        selected={{ project_id: 'new', name: '新项目', status: 'READY', governed_contract_id: 'contract-1', governed_contract_version: 3 }}
        runs={[{ run_id: 'run-1', lifecycle: 'COMPLETED', verdict: 'PASS' }]}
        onSelect={vi.fn()}
        onContinue={vi.fn()}
        onRegister={vi.fn()}
        loading={false}
      />,
    )

    const newest = screen.getAllByText('新项目')[0]
    const oldest = screen.getByText('旧项目')
    expect(newest.compareDocumentPosition(oldest) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(newest).toBeInTheDocument()
    expect(screen.getByText('READY')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('已绑定')).toBeInTheDocument()
    expect(screen.getByText('COMPLETED · PASS')).toBeInTheDocument()
    expect(screen.getByText('高级配置（ExecutionProfile、已有应用与继续入口）')).toBeInTheDocument()
    expect(screen.queryByText(/YAML\s+项目/)).not.toBeInTheDocument()
  })
})
