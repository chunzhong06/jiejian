/* 正式报告面板测试：确认已发布 HTML view、打开链接和导出菜单复用同一报告选择。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ReportPanel } from './ReportPanel'

const reportsApi = vi.hoisted(() => ({
  reports: vi.fn(),
  reportView: vi.fn((runId: string, reportId: string) => `/api/runs/${encodeURIComponent(runId)}/reports/${encodeURIComponent(reportId)}/view`),
  reportFormat: vi.fn((runId: string, reportId: string, format: string) => `/api/runs/${encodeURIComponent(runId)}/reports/${encodeURIComponent(reportId)}/formats/${format}`),
}))
const runsApi = vi.hoisted(() => ({ run: vi.fn() }))

vi.mock('../../api/results', () => ({ resultsApi: reportsApi }))
vi.mock('../../api/runs', () => ({ runsApi }))

describe('ReportPanel', () => {
  it('使用同一编码后的 view URL、沙箱 iframe 和四项导出菜单', async () => {
    const runId = 'run/with space'
    const reportId = 'report/with space'
    const secondReportId = 'report/second'
    runsApi.run.mockResolvedValue({ run_id: runId, result_integrity: 'VERIFIED' })
    reportsApi.reports.mockResolvedValue([
      { report_id: reportId, gate_decision: 'PASS' },
      { report_id: secondReportId },
    ])

    render(<ReportPanel run={{ run_id: runId }} onError={vi.fn()} />)

    const iframe = await screen.findByTitle('界鉴权限安全检查报告')
    const expectedViewUrl = `/api/runs/run%2Fwith%20space/reports/report%2Fwith%20space/view`
    const actualResults = await vi.importActual<typeof import('../../api/results')>('../../api/results')
    expect(actualResults.resultsApi.reportView(runId, reportId)).toBe(expectedViewUrl)
    expect(iframe).toHaveAttribute('src', expectedViewUrl)
    expect(iframe).toHaveAttribute('sandbox')
    expect(reportsApi.reportView).toHaveBeenCalledWith(runId, reportId)

    const openLink = screen.getByRole('link', { name: '在新窗口打开' })
    expect(openLink).toHaveAttribute('href', expectedViewUrl)
    expect(openLink).toHaveAttribute('target', '_blank')
    expect(openLink).toHaveAttribute('rel', 'noopener noreferrer')

    fireEvent.mouseDown(screen.getByRole('combobox', { name: '选择完整报告' }))
    fireEvent.click(await screen.findByTitle('检查报告 2 · 基础报告'))
    const secondViewUrl = '/api/runs/run%2Fwith%20space/reports/report%2Fsecond/view'
    await waitFor(() => expect(iframe).toHaveAttribute('src', secondViewUrl))
    expect(openLink).toHaveAttribute('href', secondViewUrl)
    expect(reportsApi.reportView).toHaveBeenCalledWith(runId, secondReportId)

    fireEvent.click(screen.getByRole('button', { name: /导出/ }))
    expect(await screen.findByText('HTML')).toHaveAttribute(
      'href',
      '/api/runs/run%2Fwith%20space/reports/report%2Fsecond/formats/html',
    )
    expect(screen.getByText('JSON')).toBeInTheDocument()
    expect(screen.getByText('SARIF')).toBeInTheDocument()
    expect(screen.getByText('JUnit')).toBeInTheDocument()
    expect(screen.queryByText('JSON.stringify')).not.toBeInTheDocument()
  })
})
