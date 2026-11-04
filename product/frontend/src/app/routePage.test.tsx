import {act,render,screen} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {routePage} from '../shared/lib/routePage'
import {refreshCurrentPage} from '../shared/lib/pageRefresh'

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

it('页面模块读取失败后由统一刷新恢复，离开后不再重试该模块',async()=>{
  const read=vi.fn().mockRejectedValueOnce(new Error('模块暂不可用')).mockResolvedValue({default:()=> <h1>已恢复页面</h1>})
  const Page=routePage(read,'/permissions'),view=render(<Page/>)
  expect(await screen.findByText('模块暂不可用')).toBeVisible()
  await act(async()=>{await refreshCurrentPage()})
  expect(screen.getByRole('heading',{name:'已恢复页面'})).toBeVisible()
  expect(read).toHaveBeenCalledTimes(2)
  view.unmount()
  await refreshCurrentPage()
  expect(read).toHaveBeenCalledTimes(2)
})
