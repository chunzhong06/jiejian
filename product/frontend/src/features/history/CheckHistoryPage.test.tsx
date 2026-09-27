// 验证历史分页、项目隔离与详情返回，不以列表操作创建新的检查。
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CheckHistoryItem, CheckHistoryPage as HistoryPage } from '../../api/currentChecks'
import { CheckHistoryPage } from './CheckHistoryPage'

const api = vi.hoisted(() => ({ history: vi.fn(), submit: vi.fn() }))
vi.mock('../../api/currentChecks', () => ({ currentChecksApi: api }))
const item = (id: string, project = 'p1'): CheckHistoryItem => ({ status: { run: { run_id: id, project_id: project, lifecycle: 'COMPLETED', verdict: 'PASS', plan_fingerprint: 'f'.repeat(64), policy_epoch: 1, created_at_us: 1780000000000000, finished_at_us: 1780000000000001 }, job: null, progress: null, result_integrity: 'VALID' }, action_labels: ['完整导出'], change_id: null, source_run_id: null })
const page = (items = [item('r1')], next_cursor: HistoryPage['next_cursor'] = null): HistoryPage => ({ project_id: 'p1', items, next_cursor })
const error = vi.fn()
function Harness() {
  const [run, setRun] = useState<string | null>(null)
  return <CheckHistoryPage project={{ project_id: 'p1', name: '项目' }} onError={error} requestedRunId={run}
    onNavigate={path => setRun(new URLSearchParams(path.split('?')[1]).get('run_id'))}
    renderRun={(id, onBack) => <section><h1>精确结果 {id}</h1><button onClick={onBack}>返回历史</button></section>} />
}
beforeEach(() => { vi.clearAllMocks(); api.history.mockResolvedValue(page()); vi.spyOn(window, 'scrollTo').mockImplementation(() => {}) })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('独立检查历史', () => {
  it('有界空页保留继续入口，只有明确操作才读取下一段', async () => {
    const cursor = { created_at_us: 12, run_id: 'cursor' }
    api.history.mockResolvedValueOnce(page([], cursor)).mockResolvedValueOnce(page([item('older')]))
    render(<Harness />)
    expect(await screen.findByText('这一段记录中没有匹配项')).toBeInTheDocument()
    expect(api.history).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: '继续读取更早记录' }))
    expect(await screen.findByText('older')).toBeInTheDocument()
    expect(api.history.mock.calls[1][1].cursor).toEqual(cursor)
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('进入指定Run并返回后保留筛选、列表和选中行', async () => {
    render(<Harness />)
    await screen.findByText('r1')
    fireEvent.change(screen.getByRole('textbox', { name: '搜索检查历史' }), { target: { value: '完整' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    await waitFor(() => expect(api.history).toHaveBeenCalledTimes(2))
    fireEvent.click(await screen.findByRole('button', { name: /完整导出.*r1/ }))
    expect(await screen.findByRole('heading', { name: '精确结果 r1' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '返回历史' }))
    expect(screen.getByRole('textbox', { name: '搜索检查历史' })).toHaveValue('完整')
    expect(screen.getByText('r1')).toBeVisible()
    expect(api.history).toHaveBeenCalledTimes(2)
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('拒绝另一项目的列表，并允许只读重试', async () => {
    api.history.mockResolvedValueOnce({ ...page([item('foreign', 'p2')]), project_id: 'p2' }).mockResolvedValueOnce(page())
    render(<Harness />)
    expect(await screen.findByRole('alert')).toHaveTextContent('历史记录读取失败')
    expect(screen.queryByText('foreign')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重试读取' }))
    expect(await screen.findByText('r1')).toBeInTheDocument()
    expect(error).toHaveBeenCalledTimes(1)
  })
  it('损坏结果不显示持久PASS，生命周期仍独立可见', async () => {
    const value = item('bad'); value.status.result_integrity = 'INVALID'; value.status.run.lifecycle = 'FAILED'; value.action_labels = []
    api.history.mockResolvedValue(page([value]))
    render(<Harness />)
    expect(await screen.findByText('结果完整性校验失败')).toBeInTheDocument()
    expect(screen.getAllByText('检查失败').length).toBeGreaterThan(0)
    expect(screen.queryByText('通过', { selector: '.history-verdict' })).not.toBeInTheDocument()
  })
  it('拒绝不推进的游标，保留已有记录并停止自动读取', async () => {
    const cursor = { created_at_us: 12, run_id: 'cursor' }
    api.history.mockResolvedValueOnce(page([item('r1')], cursor)).mockResolvedValueOnce(page([item('r2')], cursor))
    render(<Harness />)
    fireEvent.click(await screen.findByRole('button', { name: '继续读取更早记录' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('r1')).toBeInTheDocument()
    expect(screen.queryByText('r2')).not.toBeInTheDocument()
    expect(api.history).toHaveBeenCalledTimes(2)
  })
  it('项目切换后丢弃延迟返回的旧列表', async () => {
    let resolveOld!: (value: HistoryPage) => void
    api.history.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve })).mockResolvedValueOnce({ ...page([item('new', 'p2')]), project_id: 'p2' })
    const props = { onError: error, onNavigate: vi.fn(), renderRun: () => null }
    const view = render(<CheckHistoryPage {...props} project={{ project_id: 'p1' }} />)
    view.rerender(<CheckHistoryPage {...props} project={{ project_id: 'p2' }} />)
    expect(await screen.findByText('new')).toBeInTheDocument()
    resolveOld(page([item('old')]))
    await waitFor(() => expect(screen.queryByText('old')).not.toBeInTheDocument())
    expect(screen.getByText('new')).toBeInTheDocument()
  })
})
