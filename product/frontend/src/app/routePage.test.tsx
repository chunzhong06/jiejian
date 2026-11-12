import {act,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {routePage} from '../shared/lib/routePage'
import {refreshCurrentPage} from '../shared/lib/pageRefresh'
import {TestingSections,applicationSections} from '../shared/ui/SectionNavigation'
import {LinkTabs} from '../shared/ui/Tabs'

afterEach(()=>{location.hash=''})

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
  expect(await screen.findByText('页面资源暂时未能加载，请使用右上角刷新重试。')).toBeVisible()
  expect(screen.getByRole('heading',{level:1})).toHaveTextContent('权限与覆盖')
  expect(screen.queryByText('模块暂不可用')).not.toBeInTheDocument()
  await act(async()=>{await refreshCurrentPage()})
  expect(screen.getByRole('heading',{name:'已恢复页面'})).toBeVisible()
  expect(read).toHaveBeenCalledTimes(2)
  view.unmount()
  await refreshCurrentPage()
  expect(read).toHaveBeenCalledTimes(2)
})

it.each([
  ['/testing','', '操作与材料','测试工作',4],
  ['/testing','view=plans','检查方案','测试工作',4],
  ['/testing','scenario=list','业务场景','测试工作',4],
  ['/reports','', '检查记录','测试工作',4],
  ['/application','view=business','应用与来源','应用资料',3],
] as const)('目录 %s %s 的模块等待和失败均保留准确分类',async(path,query,title,label,count)=>{
  location.hash=path+'?'+query+'&project_id=nav-app'
  let reject!:(error:Error)=>void
  const Page=routePage(()=>new Promise<{default:()=>React.JSX.Element}>((_resolve,fail)=>{reject=fail}),path)
  render(<Page/>)
  expect(screen.getByRole('navigation',{name:label}).querySelectorAll('a')).toHaveLength(count)
  await act(async()=>reject(new Error('模拟页面模块读取失败')))
  expect(screen.getByRole('heading',{name:title,level:1})).toBeVisible()
  expect(screen.getByRole('navigation',{name:label}).querySelectorAll('a')).toHaveLength(count)
  for(const link of screen.getByRole('navigation',{name:label}).querySelectorAll('a'))expect(link.getAttribute('href')).toContain('project_id=nav-app')
  expect(screen.getByText(path==='/application'?'业务角色与操作':title,{selector:'a'})).toHaveAttribute('aria-current','page')
})

it.each([
 ['/testing','action_id=action'],['/testing','view=plans&routine_id=plan'],['/testing','scenario=new'],
 ['/reports','run_id=run'],['/reports','view=plan'],['/reports','view=compare'],['/application','view=create'],
])('准确任务 %s %s 的模块失败保持任务回退，不插入目录分类',async(path,query)=>{
 location.hash=path+'?'+query+'&project_id=nav-app'
 const Page=routePage(async()=>{throw new Error('模块不可用')},path)
 render(<Page/>)
 await screen.findByText('页面资源暂时未能加载，请使用右上角刷新重试。')
 expect(screen.queryByRole('navigation',{name:'测试工作'})).not.toBeInTheDocument()
 expect(screen.queryByRole('navigation',{name:'应用资料'})).not.toBeInTheDocument()
})

it('目录恢复后只保留实际页面的一组分类，内嵌资料失败沿用外层分类',async()=>{
 location.hash='/testing?project_id=nav-app'
 const read=vi.fn().mockRejectedValueOnce(new Error('模块不可用')).mockResolvedValue({default:()=> <><h1>已恢复目录</h1><TestingSections value="materials" projectId="nav-app"/></>})
 const Page=routePage(read,'/testing'),view=render(<Page/>)
 await screen.findByText('页面资源暂时未能加载，请使用右上角刷新重试。')
 await act(async()=>{await refreshCurrentPage()})
 expect(screen.getByRole('heading',{name:'已恢复目录'})).toBeVisible()
 expect(screen.getAllByRole('navigation',{name:'测试工作'})).toHaveLength(1)
 view.unmount();location.hash='/application?view=business&project_id=nav-app'
 const Child=routePage(async()=>{throw new Error('内部模块不可用')},'/application',{embedded:true})
 render(<><h1>应用与来源</h1><LinkTabs label="应用资料" value="business" items={applicationSections.map(item=>({...item,href:'#/application?view='+item.value}))}/><Child/></>)
 await screen.findByText('页面资源暂时未能加载，请使用右上角刷新重试。')
 expect(screen.getAllByRole('navigation',{name:'应用资料'})).toHaveLength(1)
 expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1)
})
