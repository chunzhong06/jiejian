// 验收行来自精确发布记录；旧响应和损坏证据不能维持当前结论。
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { PermissionAcceptance } from './PermissionAcceptance'
import { story } from '../results/testing.fixtures'
const api = vi.hoisted(() => ({ story: vi.fn() }))
vi.mock('../../api/currentChecks', () => ({ currentChecksApi: api }))
beforeEach(() => { vi.clearAllMocks(); api.story.mockResolvedValue({ ...story(), runtime_status: 'MATCHED' }) })
it('同一行对照要求和实际后果，证据入口携带精确 Run 和 Case', async () => {
  const navigate = vi.fn()
  render(<PermissionAcceptance projectId="p1" runId="r1" onNavigate={navigate}/>)
  expect(await screen.findByText('计划成员不得导出资料')).toBeInTheDocument()
  expect(screen.getByText('完整交付包：业务交付包已确认生成')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '查看计划成员导出资料的证据' }))
  expect(navigate).toHaveBeenCalledWith('/history?run_id=r1&case_id=c1')
})
it('没有本批 Run 时不查询最近记录补成已验收', () => {
  render(<PermissionAcceptance projectId="p1" runId={null} onNavigate={vi.fn()}/>)
  expect(api.story).not.toHaveBeenCalled()
  expect(screen.getByText(/当前交付尚无关联结果/)).toBeInTheDocument()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})
it('切换批次忽略旧读取，并拒绝新请求返回其它 Run', async () => {
  let resolve!: (value: unknown) => void
  api.story.mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const view = render(<PermissionAcceptance projectId="p1" runId="r1" onNavigate={vi.fn()}/>)
  view.rerender(<PermissionAcceptance projectId="p1" runId="r2" onNavigate={vi.fn()}/>)
  await waitFor(() => expect(screen.getByText(/暂时无法核验本轮结果/)).toBeInTheDocument())
  await act(async () => resolve(story()))
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})
