// 核对源码对应的缺失、陈旧与跨项目响应不能变成当前代码的结论。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SourceIdentityPanel } from './SourceIdentityPanel'
import { ApiError } from '../../api/http'
const read = vi.hoisted(() => vi.fn())
vi.mock('../../api/sourceIdentity', () => ({ sourceIdentityApi: { read } }))
const value = () => ({ project_id: 'p1', run_id: 'r1', change_id: null, comparison: 'CHANGED', recorded: { fingerprint: 'a'.repeat(64), snapshot_id: 's1', file_count: 3, git_status: 'NOT_RECORDED' }, current_fingerprint: 'b'.repeat(64), current_git: { status: 'AVAILABLE', head: 'f'.repeat(40), has_local_changes: true }, observed_at_us: 1, target_version: 'NOT_INDEPENDENTLY_IDENTIFIED' })
const props = { projectId: 'p1', recordId: 'r1', kind: 'runs' as const, onNavigate: vi.fn() }
describe('源码对应', () => {
  beforeEach(() => { vi.clearAllMocks(); read.mockResolvedValue(value()) })
  it('分开表达历史内容、当前修改与未知部署版本', async () => {
    render(<SourceIdentityPanel {...props}/>)
    expect(await screen.findByText('当前源码已不同于这份记录')).toBeInTheDocument()
    expect(screen.getByText('源码目录含未提交修改')).toBeInTheDocument()
    expect(screen.getByText('运行目标版本 · 尚无独立标识')).toBeInTheDocument()
    expect(screen.getByText('当时的 Git 提交未记录，不能用当前提交补填。')).toBeInTheDocument()
  })
  it('读取失败保留明确未知，重新核对只发起读取', async () => {
    read.mockRejectedValueOnce(new Error('unavailable'))
    render(<SourceIdentityPanel {...props}/>)
    expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法读取源码对应')
    fireEvent.click(screen.getByRole('button', { name: '重新核对源码' }))
    expect(await screen.findByText('当前源码已不同于这份记录')).toBeInTheDocument()
    expect(read).toHaveBeenCalledTimes(2)
  })
  it('拒绝别的项目或 Run 的响应', async () => {
    read.mockResolvedValue({ ...value(), project_id: 'p2' })
    render(<SourceIdentityPanel {...props}/>)
    await screen.findByRole('alert')
    expect(screen.queryByText('当前源码已不同于这份记录')).not.toBeInTheDocument()
  })
  it('切换记录后丢弃较晚返回的旧请求', async () => {
    let resolve!: (data: unknown) => void
    read.mockImplementationOnce(() => new Promise(r => { resolve = r }))
    const page = render(<SourceIdentityPanel {...props}/>)
    read.mockResolvedValue({ ...value(), run_id: 'r2', comparison: 'SAME' })
    page.rerender(<SourceIdentityPanel {...props} recordId="r2"/>)
    await screen.findByText('记录范围内的源码内容一致')
    resolve(value())
    await waitFor(() => expect(screen.queryByText('当前源码已不同于这份记录')).not.toBeInTheDocument())
  })
  it('历史发布包损坏时通知结果页撤下旧结论', async () => {
    const onIntegrityError = vi.fn()
    read.mockRejectedValue(new ApiError('ARTIFACT_MANIFEST', '结果完整性失败'))
    render(<SourceIdentityPanel {...props} onIntegrityError={onIntegrityError}/>)
    await screen.findByRole('alert')
    expect(onIntegrityError).toHaveBeenCalledOnce()
  })
  it('Git 工作区未核对不等于无未提交修改', async () => {
    read.mockResolvedValue({ ...value(), current_git: { ...value().current_git, has_local_changes: null } })
    render(<SourceIdentityPanel {...props}/>)
    expect(await screen.findByText('已读取提交，工作区状态未核对')).toBeInTheDocument()
    expect(screen.queryByText('源码目录无未提交修改')).not.toBeInTheDocument()
  })
})
