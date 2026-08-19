import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CheckHistoryPage } from './CheckHistoryPage'

const findings = vi.hoisted(() => vi.fn())
vi.mock('../../api/results', () => ({ resultsApi: { findings } }))

describe('CheckHistoryPage', () => {
  it('按时间顺序展示真实出现/重现，不为缺失运行补消失点', async () => {
    findings.mockImplementation(async (runId: string) => runId === 'run-1'
      ? [{ finding: { finding_id: 'finding-1', identity: { permission_intent: '读取文档' } }, occurrence: { status: 'APPEARED', severity: 'high' } }]
      : runId === 'run-3'
        ? [{ finding: { finding_id: 'finding-1', identity: { permission_intent: '读取文档' } }, occurrence: { status: 'REAPPEARED', severity: 'high' } }]
        : [])
    const runs = [
      { run_id: 'run-3', created_at_us: 3, lifecycle: 'COMPLETED', result_integrity: 'VERIFIED' },
      { run_id: 'run-1', created_at_us: 1, lifecycle: 'COMPLETED', result_integrity: 'VERIFIED' },
      { run_id: 'run-2', created_at_us: 2, lifecycle: 'COMPLETED', result_integrity: 'VERIFIED' },
    ]
    render(<CheckHistoryPage runs={runs} onError={vi.fn()} />)
    expect(await screen.findByText('首次出现')).toBeInTheDocument()
    expect(await screen.findByText('再次出现')).toBeInTheDocument()
    expect(screen.queryByText('已不再出现')).not.toBeInTheDocument()
    expect(findings.mock.invocationCallOrder[0]).toBeLessThan(findings.mock.invocationCallOrder[1])
  })
})
