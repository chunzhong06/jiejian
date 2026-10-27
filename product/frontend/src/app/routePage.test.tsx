import {act,render,screen} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {routePage} from './routePage'

it('模块完成后立即替换占位，离开后不挂载旧页面',async()=>{
  let resolve!:(value:{default:()=>React.JSX.Element})=>void
  const read=vi.fn(()=>new Promise<{default:()=>React.JSX.Element}>(finish=>{resolve=finish}))
  const Page=routePage(read,'/preparation')
  const view=render(<Page/>)
  expect(screen.getByRole('status',{name:'正在读取检查准备'})).toBeVisible()
  await act(async()=>resolve({default:()=> <h1>实际材料</h1>}))
  expect(screen.getByRole('heading',{name:'实际材料'})).toBeVisible()
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  view.unmount()
  render(<Page/>)
  expect(screen.getByRole('heading',{name:'实际材料'})).toBeVisible()
  expect(read).toHaveBeenCalledTimes(1)
})

it('悬停预取只加载模块，进入页面前不挂载或读取业务',async()=>{
  const mount=vi.fn(),read=vi.fn(async()=>({default:()=>{mount();return <h1>权限规则</h1>}}))
  const Page=routePage(read,'/permissions')
  await Page.preload()
  expect(mount).not.toHaveBeenCalled()
  render(<Page/>)
  expect(screen.getByRole('heading',{name:'权限规则'})).toBeVisible()
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(read).toHaveBeenCalledTimes(1)
})
