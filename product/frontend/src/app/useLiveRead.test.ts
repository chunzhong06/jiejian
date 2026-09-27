// 验证长时间只读跟踪、暂时失败恢复和并发请求边界。
import { act, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useLiveRead } from './useLiveRead'
afterEach(()=>vi.useRealTimers())
it('超过五分钟仍同步，暂时失败后自动恢复', async()=>{
  vi.useFakeTimers()
  const read=vi.fn().mockResolvedValue(undefined)
  const view=renderHook(()=>useLiveRead('p1',read,2000))
  await act(async()=>{await vi.advanceTimersByTimeAsync(310000)})
  expect(read.mock.calls.length).toBeGreaterThan(150)
  read.mockRejectedValueOnce(new Error('offline'))
  await act(async()=>{await vi.advanceTimersByTimeAsync(2000)})
  expect(view.result.current.retrying).toBe(true)
  await act(async()=>{await vi.advanceTimersByTimeAsync(4000)})
  expect(view.result.current.retrying).toBe(false)
  view.unmount()
})
it('失焦恢复触发读取，但慢请求不并发，卸载后不继续',async()=>{
  vi.useFakeTimers()
  let finish!:()=>void
  const read=vi.fn().mockImplementation(()=>new Promise<void>(resolve=>{finish=resolve}))
  const view=renderHook(()=>useLiveRead('p1',read,2000))
  await act(async()=>{window.dispatchEvent(new Event('focus'));await vi.advanceTimersByTimeAsync(10000)})
  expect(read).toHaveBeenCalledTimes(1)
  view.unmount()
  await act(async()=>{finish();await vi.advanceTimersByTimeAsync(10000)})
  expect(read).toHaveBeenCalledTimes(1)
})
