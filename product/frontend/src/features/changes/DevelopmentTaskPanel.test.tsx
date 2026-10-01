// 取消任务须明确确认并保留稳定回执；查看已有验收不创建新检查。
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { DevelopmentTaskPanel } from './DevelopmentTaskPanel'
import type { DevelopmentView } from '../../api/development'
const api = vi.hoisted(() => ({ finish: vi.fn() }))
vi.mock('../../api/development', async () => ({ ...await vi.importActual<typeof import('../../api/development')>('../../api/development'), developmentApi: api }))
const value = { task: { task_id: 't', project_id: 'p', version: 3, revision: 1 }, context: { title: '当前目标', goal: '维持权限', context_id: 'ctx', permission_refs: [] }, acceptance: null, deliveries: [{ change_id: 'batch', ordinal: 2 }], runtime_state: 'MATCHED', latest_verification: { run_id: 'run', verdict: 'PASS' } } as unknown as DevelopmentView
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear() })
it('取消先说明保留历史，确认后只登记一次取消并等待刷新', async () => {
  api.finish.mockImplementation((_project, _task, body) => Promise.resolve({ project_id: 'p', operation_id: body.operation_id }))
  const changed = vi.fn().mockResolvedValue(undefined)
  render(<DevelopmentTaskPanel projectId="p" value={value} disabled={false} onChanged={changed} onError={vi.fn()} onSelectChange={vi.fn()} onNavigate={vi.fn()}/>)
  fireEvent.click(screen.getByRole('button', { name: '取消任务' }))
  expect(api.finish).not.toHaveBeenCalled()
  expect(screen.getByText('停止继续推进此目标，已登记的交付和检查历史仍然保留。')).toBeInTheDocument()
  fireEvent.click(within(screen.getByRole('tooltip')).getByRole('button', { name: '取消任务' }))
  await waitFor(() => expect(changed).toHaveBeenCalledOnce())
  expect(api.finish).toHaveBeenCalledExactlyOnceWith('p', 't', expect.objectContaining({ action: 'CANCEL', expected_version: 3, operation_id: expect.stringMatching(/^[a-f0-9]{32}$/) }))
})
it('主操作直接打开本批已发布检查，而不是重新检查', () => {
  const navigate = vi.fn()
  render(<DevelopmentTaskPanel projectId="p" value={value} disabled={false} onChanged={vi.fn()} onError={vi.fn()} onSelectChange={vi.fn()} onNavigate={navigate}/>)
  fireEvent.click(screen.getByRole('button', { name: '查看本批检查结果' }))
  expect(navigate).toHaveBeenCalledExactlyOnceWith('/history?run_id=run')
  expect(api.finish).not.toHaveBeenCalled()
})
