// 只有明确资源不一致才提示更新；关闭、编辑保护和主动刷新不会触发业务写入。
import {cleanup, fireEvent, render, screen} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {FrontendBuildNotice} from './FrontendBuildNotice'
import {frontendBuildId, frontendIdentityState} from '../../shared/runtime/buildIdentity'

afterEach(cleanup)
const newer={status:'CONFIRMED' as const,build_id:'b'.repeat(64),reason:'已核对'}

it('缺少任一侧身份不能声称当前或提示更新',()=>{
  expect(frontendIdentityState(undefined,'a')).toBe('UNCONFIRMED')
  expect(frontendIdentityState(newer,null)).toBe('UNCONFIRMED')
  expect(frontendIdentityState({...newer,status:'UNCONFIRMED'},'a')).toBe('UNCONFIRMED')
  render(<FrontendBuildNotice identity={undefined} blocked={false}/>)
  expect(screen.queryByRole('region',{name:'页面资源更新'})).not.toBeInTheDocument()
})

it('一致资源不显示更新卡片',()=>{
  render(<FrontendBuildNotice identity={{...newer,build_id:frontendBuildId}} blocked={false}/>)
  expect(screen.queryByRole('button',{name:'刷新页面'})).not.toBeInTheDocument()
})

it('有未保存工作或活动检查时禁止刷新，解除后仍需明确点击',()=>{
  const reload=vi.fn()
  const view=render(<FrontendBuildNotice identity={newer} blocked onReload={reload}/>)
  expect(screen.getByRole('button',{name:'刷新页面'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'刷新页面'}));expect(reload).not.toHaveBeenCalled()
  view.rerender(<FrontendBuildNotice identity={newer} blocked={false} onReload={reload}/>)
  expect(reload).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'刷新页面'}));expect(reload).toHaveBeenCalledOnce()
})

it('关闭只忽略当前更新，下一份资源仍可提示',()=>{
  const view=render(<FrontendBuildNotice identity={newer} blocked={false}/>)
  fireEvent.click(screen.getByRole('button',{name:'关闭页面更新提示'}))
  expect(screen.queryByRole('button',{name:'刷新页面'})).not.toBeInTheDocument()
  view.rerender(<FrontendBuildNotice identity={{...newer,build_id:'c'.repeat(64)}} blocked={false}/>)
  expect(screen.getByRole('button',{name:'刷新页面'})).toBeEnabled()
})
