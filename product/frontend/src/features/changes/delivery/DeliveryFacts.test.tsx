// 验证批次差异和精确结果导航；相同源码的其它记录不能替代当前交付。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { DeliveryFacts } from './DeliveryFacts'
import type { SourceChangeViewDto } from '../../../api/changes/sourceChanges'
const api = vi.hoisted(() => ({ details: vi.fn() }))
vi.mock('../../../api/changes/development', () => ({ developmentApi: api }))
const change = { manifest: { change_id: 'c2', project_id: 'p', claimed_paths: ['second.py'] }, change_set: { status: 'COMPARABLE', added_paths: [], modified_paths: ['second.py'], removed_paths: [] }, revalidation: { can_execute: true } } as unknown as SourceChangeViewDto
const details = { project_id: 'p', delivery: { project_id: 'p', task_id: 't', context_id: 'ctx', delivery_id: 'd2', change_id: 'c2', ordinal: 2 }, context: { context_id: 'ctx', project_id: 'p', task_id: 't', permission_refs: [], revision: 1, goal: '继续优化' }, relative_change: change.change_set, cumulative_change: { ...change.change_set, modified_paths: ['first.py', 'second.py'] }, verification: { run_id: 'exact', verdict: 'PASS', runtime_status: 'MATCHED', repair_status: null } }
beforeEach(() => { vi.clearAllMocks(); api.details.mockResolvedValue(details) })
it('切换累计差异仍读取已保存快照，结果只跳精确批次且不出现再次检查按钮', async () => {
  const navigate = vi.fn(); render(<DeliveryFacts projectId="p" change={change} onNavigate={navigate} onError={vi.fn()}/>)
  await screen.findByRole('heading', { name: '本批权限要求已验证' })
  expect(screen.queryByText('first.py')).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('相对起始快照'))
  expect(screen.getByText('first.py')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '查看本批检查记录' }))
  expect(navigate).toHaveBeenCalledWith('/history?run_id=exact')
  expect(screen.queryByRole('button', { name: '检查这次变化' })).not.toBeInTheDocument()
})
it('跨项目的交付详情撤下验收结论', async () => {
  api.details.mockResolvedValue({ ...details, project_id: 'other' })
  const error = vi.fn(); render(<DeliveryFacts projectId="p" change={change} onNavigate={vi.fn()} onError={error}/>)
  await waitFor(() => expect(error).toHaveBeenCalled())
  expect(screen.queryByRole('heading', { name: '本批权限要求已验证' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '查看本批检查记录' })).not.toBeInTheDocument()
})
