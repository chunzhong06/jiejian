import {act,renderHook,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {useRead} from './useRead'
import {refreshCurrentPage} from './pageRefresh'
import {useState} from 'react'

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

it('统一刷新由同一读取所有者接收结果，保留草稿、已有内容并合并连续点击',async()=>{
  let finish!:(value:string)=>void
  const manual=vi.fn(()=>new Promise<string>(resolve=>{finish=resolve})),read=vi.fn().mockResolvedValue('saved facts')
  const view=renderHook(()=>{const [draft,setDraft]=useState('未提交内容');return {state:useRead('refresh-item',read,0,manual),draft,setDraft}})
  await waitFor(()=>expect(view.result.current.state.data).toBe('saved facts'))
  let first!:Promise<void>,second!:Promise<void>
  act(()=>{first=refreshCurrentPage();second=refreshCurrentPage()})
  expect(first).toBe(second)
  expect(manual).toHaveBeenCalledOnce()
  expect(view.result.current.state.data).toBe('saved facts')
  expect(view.result.current.state.loading).toBe(false)
  await act(async()=>{finish('fresh facts');await first})
  expect(view.result.current.state.data).toBe('fresh facts')
  expect(view.result.current.draft).toBe('未提交内容')
  expect(read).toHaveBeenCalledOnce()
  view.unmount()
  await refreshCurrentPage()
  expect(manual).toHaveBeenCalledOnce()
})

it('统一刷新恢复读取失败的区域，不中断其他区域或在途请求',async()=>{
  const failed=vi.fn().mockRejectedValueOnce(new Error('暂不可读')).mockResolvedValue('recovered')
  let finish!:(value:string)=>void
  const pending=vi.fn(()=>new Promise<string>(resolve=>{finish=resolve}))
  const view=renderHook(()=>({failed:useRead('failure',failed),pending:useRead('pending',pending)}))
  await waitFor(()=>expect(view.result.current.failed.error?.message).toBe('暂不可读'))
  await act(async()=>{await refreshCurrentPage()})
  expect(view.result.current.failed.data).toBe('recovered')
  expect(view.result.current.failed.error).toBeUndefined()
  expect(pending).toHaveBeenCalledOnce()
  await act(async()=>finish('original response'))
  expect(view.result.current.pending.data).toBe('original response')
})

it('更新失败保留最近成功时间和正文，换对象不借用旧事实',async()=>{
  const request=vi.fn().mockResolvedValueOnce('known').mockRejectedValueOnce(new Error('offline'))
  const view=renderHook(({key})=>useRead(key,request),{initialProps:{key:'a'}})
  await waitFor(()=>expect(view.result.current.status).toBe('ready'))
  const received=view.result.current.receivedAt
  act(()=>view.result.current.reload())
  await waitFor(()=>expect(view.result.current.status).toBe('stale'))
  expect(view.result.current.data).toBe('known');expect(view.result.current.receivedAt).toBe(received)
  request.mockResolvedValueOnce('new object')
  view.rerender({key:'b'})
  await waitFor(()=>expect(view.result.current.data).toBe('new object'))
  expect(view.result.current.error).toBeUndefined()
})
