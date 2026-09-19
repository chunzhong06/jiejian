// 全局检查通知只跟踪真实Run，终态和完整性分开，不触发导航或提交。
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { CheckStatus } from '../api/currentChecks'
import { useCheckActivity } from './useCheckActivity'
const api = vi.hoisted(() => ({ status: vi.fn(), submit: vi.fn() }))
vi.mock('../api/currentChecks', () => ({ currentChecksApi: api }))
const active: CheckStatus = { run: { project_id: 'p1', run_id: 'r1', lifecycle: 'RUNNING', verdict: null, plan_fingerprint: 'x', policy_epoch: 1, created_at_us: 1, finished_at_us: null }, progress: null, job: null, result_integrity: 'NOT_PUBLISHED' }
beforeEach(() => { vi.clearAllMocks() })
afterEach(() => vi.useRealTimers())
it('不通知首次恢复的旧结果，但补获轮询间隙已经结束的新检查', async () => {
  api.status.mockResolvedValue({...active,run:{...active.run,run_id:'r2',lifecycle:'COMPLETED',verdict:'PASS'},result_integrity:'VALID'})
  const refresh=vi.fn()
  const view=renderHook(({latest})=>useCheckActivity('p1',null,refresh,latest,true),{initialProps:{latest:'r1'}})
  expect(api.status).not.toHaveBeenCalled()
  view.rerender({latest:'r2'})
  await waitFor(()=>expect(view.result.current.completed?.runId).toBe('r2'))
  expect(api.status).toHaveBeenCalledWith('r2');expect(api.submit).not.toHaveBeenCalled()
})
it('完整性未通过时不把持久PASS用作完成通知', async () => {
  api.status.mockResolvedValue({ ...active, run: { ...active.run, lifecycle: 'COMPLETED', verdict: 'PASS' }, result_integrity: 'INVALID' })
  const refresh = vi.fn().mockResolvedValue(undefined); const { result } = renderHook(() => useCheckActivity('p1', active, refresh))
  await waitFor(() => expect(result.current.completed?.label).toBe('检查已结束，结果完整性校验失败'))
  expect(refresh).toHaveBeenCalledTimes(1); expect(api.submit).not.toHaveBeenCalled()
  act(() => result.current.dismiss()); expect(result.current.completed).toBeNull()
})
it('只读失败保留同步暂停状态，不重试副作用', async () => {
  api.status.mockRejectedValue(new Error('read unavailable'))
  const refresh = vi.fn(); const { result } = renderHook(() => useCheckActivity('p1', active, refresh))
  await waitFor(() => expect(result.current.paused).toBe(true))
  expect(result.current.completed).toBeNull(); expect(api.status).toHaveBeenCalledTimes(1); expect(refresh).not.toHaveBeenCalled()
})
it('卸载后迟到的终态不通知新页面', async () => {
  let finish!: (status: CheckStatus) => void
  api.status.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const refresh = vi.fn(); const view = renderHook(() => useCheckActivity('p1', active, refresh))
  view.unmount()
  await act(async () => finish({ ...active, run: { ...active.run, lifecycle: 'COMPLETED', verdict: 'PASS' }, result_integrity: 'VALID' }))
  expect(refresh).not.toHaveBeenCalled()
})
