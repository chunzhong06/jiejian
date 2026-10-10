// 验证可选规则匹配按需读取、保持精确修订并隔离迟到响应。
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { RuleCoveragePreview } from './RuleCoveragePreview'
const api=vi.hoisted(()=>({read:vi.fn()}))
vi.mock('../../api/boundaries/rulePreview',()=>({rulePreviewApi:api}))
const reference={kind:'PROPOSAL' as const,proposal_id:'proposal-a'}
const value={project_id:'app-a',availability:'AVAILABLE',coverage:null,matches:[],actors:[{id:'actor',label:'负责人'}],actions:[{id:'action',label:'预览作品',effects:[{id:'effect',label:'公开内容可见'}]}]}
const open=()=>{const details=screen.getByText('试一下这些规则怎样适用').closest('details')!;details.open=true;fireEvent(details,new Event('toggle'))}
beforeEach(()=>{vi.resetAllMocks();api.read.mockResolvedValue(value)})

it('折叠时不读取，展开只查询精确提案，未选情境不能执行查询',async()=>{
  render(<RuleCoveragePreview projectId="app-a" reference={reference}/> )
  expect(api.read).not.toHaveBeenCalled();open()
  expect(await screen.findByRole('combobox',{name:'谁来操作'})).toBeInTheDocument()
  expect(api.read).toHaveBeenCalledWith('app-a',reference,undefined)
  expect(screen.getByRole('button',{name:'查看规则如何适用'})).toBeDisabled()
})

it('项目切换后不展示旧请求的允许结果',async()=>{
  let release!:(value:unknown)=>void
  api.read.mockImplementation((project:string)=>project==='app-a'?new Promise(resolve=>{release=resolve}):Promise.resolve({...value,project_id:'app-b',availability:'NEEDS_DECISION'}))
  const view=render(<RuleCoveragePreview projectId="app-a" reference={reference}/>);open()
  await waitFor(()=>expect(api.read).toHaveBeenCalledOnce())
  view.rerender(<RuleCoveragePreview projectId="app-b" reference={{kind:'PROPOSAL',proposal_id:'proposal-b'}}/>)
  expect(await screen.findByText('先完成含义核对，再查看规则怎样适用。')).toBeInTheDocument()
  await act(async()=>release({...value,coverage:'ALLOW'}))
  expect(screen.queryByText(/这组规则允许/)).not.toBeInTheDocument()
})

it('匹配请求使用当前情境，改变选项即清除旧答案',async()=>{
  api.read.mockImplementation((_project,_reference,situation)=>Promise.resolve({...value,coverage:situation?'ALLOW':null,matches:situation?[{permission_item_id:'p1'}]:[]}))
  render(<RuleCoveragePreview projectId="app-a" reference={reference}/>);open()
  const select=async(name:string,label:string)=>{
    fireEvent.mouseDown(await screen.findByRole('combobox',{name}))
    const options=await screen.findAllByText(label)
    fireEvent.click(options.filter(item=>item.closest('.ant-select-item-option')).at(-1)!)
  }
  await select('谁来操作','负责人');await select('资源属于谁','负责人');await select('资源关系','自己的资源')
  await select('执行什么动作','预览作品');await select('观察哪个结果','公开内容可见')
  fireEvent.click(screen.getByRole('button',{name:'查看规则如何适用'}))
  expect(await screen.findByText('这组规则允许这个角色执行该动作，并取得所选结果。')).toBeInTheDocument()
  expect(api.read).toHaveBeenLastCalledWith('app-a',reference,{subject_id:'actor',owner_id:'actor',relation:'OWNS',action_id:'action',effect_id:'effect'})
  await select('资源关系','同角色另一账号的资源')
  expect(screen.queryByText('这组规则允许这个角色执行该动作，并取得所选结果。')).not.toBeInTheDocument()
})
