import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {ErrorNote,PageError} from './feedback'
import {ApiError} from '../api/http'
import {subscribePageRefresh} from '../lib/pageRefresh'

it('读取失败就近恢复，只通知原读取所有者且不重挂载页面',async()=>{
 const read=vi.fn().mockResolvedValue(undefined),unsubscribe=subscribePageRefresh(read)
 try{
  render(<><input aria-label="保留草稿" defaultValue="原输入"/><PageError title="检查准备" error={new Error('连接暂时中断')}/></>)
  fireEvent.click(screen.getByRole('button',{name:'重新读取当前内容'}))
  await waitFor(()=>expect(read).toHaveBeenCalledOnce())
  expect(screen.getByLabelText('保留草稿')).toHaveValue('原输入')
 }finally{unsubscribe()}
})

it('失败首层给出原因和恢复，诊断引用按需读取且不改变原恢复动作',()=>{
 const retry=vi.fn()
 render(<ErrorNote error={new ApiError('READ_FAILED','检查材料暂时未能读取','trace-test')} onRetry={retry} retryLabel="重新读取材料"/>)
 expect(screen.getByText('检查材料暂时未能读取')).toBeVisible()
 expect(screen.getByText('trace-test')).not.toBeVisible()
 fireEvent.click(screen.getByRole('button',{name:'重新读取材料'}))
 expect(retry).toHaveBeenCalledOnce()
 expect(screen.getByRole('alert')).toHaveTextContent('trace-test')
})
