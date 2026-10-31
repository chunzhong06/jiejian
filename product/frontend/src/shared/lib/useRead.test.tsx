import {act,renderHook,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {useRead} from './useRead'

it('较晚返回的旧对象不能覆盖当前对象，离开时取消旧读取',async()=>{
  let resolveOld!:(value:string)=>void
  const pending=new Promise<string>(resolve=>{resolveOld=resolve})
  let oldSignal:AbortSignal|undefined
  const read=vi.fn((key:string,signal:AbortSignal)=>{if(key==='old'){oldSignal=signal;return pending}return Promise.resolve('current facts')})
  const view=renderHook(({key})=>useRead(key,signal=>read(key,signal)),{initialProps:{key:'old'}})
  view.rerender({key:'new'})
  await waitFor(()=>expect(view.result.current.data).toBe('current facts'))
  expect(oldSignal?.aborted).toBe(true)
  await act(async()=>resolveOld('stale facts'))
  expect(view.result.current.data).toBe('current facts')
})

it('显式重新读取保留已经显示的数据',async()=>{
  let finish!:(value:string)=>void
  const second=new Promise<string>(resolve=>{finish=resolve})
  const read=vi.fn().mockResolvedValueOnce('saved facts').mockReturnValueOnce(second)
  const view=renderHook(()=>useRead('item',read))
  await waitFor(()=>expect(view.result.current.data).toBe('saved facts'))
  act(()=>view.result.current.reload())
  expect(view.result.current.data).toBe('saved facts')
  expect(view.result.current.loading).toBe(false)
  await act(async()=>finish('fresh facts'))
  expect(view.result.current.data).toBe('fresh facts')
})

it('同一轮焦点与可见性恢复只刷新一次，卸载后不再读取',async()=>{
  const read=vi.fn().mockResolvedValue('facts')
  const view=renderHook(()=>useRead('item',read))
  await waitFor(()=>expect(view.result.current.data).toBe('facts'))
  act(()=>{window.dispatchEvent(new Event('focus'));document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('online'))})
  await waitFor(()=>expect(read).toHaveBeenCalledTimes(2))
  view.unmount()
  window.dispatchEvent(new Event('focus'))
  await new Promise(resolve=>setTimeout(resolve,10))
  expect(read).toHaveBeenCalledTimes(2)
})
