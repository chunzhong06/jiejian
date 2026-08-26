import { fireEvent, render, screen } from '@testing-library/react'
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
        onConnected={vi.fn()}
        onUnderstandingChanged={vi.fn()}
        onContinue={vi.fn()}
        onRegister={vi.fn()}
        loading={false}
      />,
    )

    expect(screen.queryByText('4. 确认角色与关键操作')).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText('D:\\profiles\\profile.json')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('高级配置（已有 Profile 项目）'))

    const newest = screen.getAllByText('新项目')[0]
    const oldest = screen.getByText('旧项目')
    expect(newest.compareDocumentPosition(oldest) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(newest).toBeInTheDocument()
    expect(screen.getAllByText('已就绪').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('已绑定')).toBeInTheDocument()
    expect(screen.getByText('已完成 · 当前规则覆盖范围内未发现越权')).toBeInTheDocument()
    expect(screen.getByText('高级配置（已有 Profile 项目）')).toBeInTheDocument()
    expect(screen.queryByText('旧版手工快速检查（高级）')).not.toBeInTheDocument()
    expect(screen.queryByText(/YAML\s+项目/)).not.toBeInTheDocument()
  })
})
