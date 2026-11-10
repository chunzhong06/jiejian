import {act,renderHook} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {readPending,useCommand,notAccepted,savePending} from './operations'
import {ApiError} from '../api/http'

it('只有明确未接纳且没有更早未知时才解除原请求',()=>{
  const rejected=new ApiError('STATE_PRECONDITION','未接纳',undefined,undefined,false,undefined,'NOT_ACCEPTED')
  expect(notAccepted(rejected)).toBe(true)
  expect(notAccepted(rejected,true)).toBe(false)
  expect(notAccepted(new ApiError('INPUT_INVALID','没有接纳证明'))).toBe(false)
  expect(notAccepted(new Error('not accepted'))).toBe(false)
})

it('取得回执后清除本地恢复记录失败不会改写成功结果',()=>{
  const clear=vi.spyOn(Storage.prototype,'removeItem').mockImplementation(()=>{throw new DOMException('storage unavailable')})
  try{expect(()=>savePending('finished',undefined)).not.toThrow()}finally{clear.mockRestore()}
})

it('同一命令在等待中不重复执行，结果未知时不自动重发',async()=>{
  let reject!:(error:Error)=>void
  const request=vi.fn(()=>new Promise<void>((_,fail)=>{reject=fail}))
  const view=renderHook(()=>useCommand('app:save'))
  let pending!:Promise<unknown>
  act(()=>{pending=view.result.current.run(request,'write');void view.result.current.run(request,'write')})
  expect(request).toHaveBeenCalledOnce()
  expect(view.result.current.busy).toBe(true)
  await act(async()=>{reject(new Error('connection lost'));await pending})
  expect(view.result.current.phase).toBe('unknown')
  expect(request).toHaveBeenCalledOnce()
})

it('切换作用域和卸载后旧命令不覆盖新状态或报告旧错误',async()=>{
  const error=vi.fn()
  let fail!:(error:Error)=>void
  const view=renderHook(({scope})=>useCommand(scope,error),{initialProps:{scope:'old'}})
  let old!:Promise<unknown>
  act(()=>{old=view.result.current.run(()=>new Promise<void>((_,reject)=>{fail=reject}),'write')})
  view.rerender({scope:'new'})
  await act(async()=>{await view.result.current.run(async()=>42)})
  await act(async()=>{fail(new Error('late'));await old})
  expect(view.result.current.phase).toBe('confirmed')
  expect(error).not.toHaveBeenCalled()
  view.unmount()
})

it('明确拒绝与不合法恢复形状分别处理',async()=>{
  const view=renderHook(()=>useCommand('app',undefined,error=>error==='rejected'))
  await act(async()=>{await view.result.current.run(async()=>{throw 'rejected'},'write')})
  expect(view.result.current.phase).toBe('rejected')
  sessionStorage.setItem('malformed-recovery','{"operation":[]}')
  const saved=readPending('malformed-recovery',(value):value is {operation:string}=>
    Boolean(value)&&typeof value==='object'&&typeof (value as {operation?:unknown}).operation==='string')
  expect(saved).toBeUndefined()
  expect(sessionStorage.getItem('malformed-recovery')).toBe('{"operation":[]}')
  expect(()=>savePending('malformed-recovery',{operation:'new'})).toThrow('原请求可能已经执行')
})


it('浏览器存储不可用时不阻断工作面读取',()=>{
  const read=vi.spyOn(Storage.prototype,'getItem').mockImplementation(()=>{throw new DOMException('unavailable','SecurityError')})
  const remove=vi.spyOn(Storage.prototype,'removeItem').mockImplementation(()=>{throw new DOMException('unavailable','SecurityError')})
  try { expect(readPending('restricted-recovery')).toBeUndefined() }
  finally { read.mockRestore();remove.mockRestore() }
})
