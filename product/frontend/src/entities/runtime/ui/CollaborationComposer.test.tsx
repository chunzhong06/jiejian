import {useState} from 'react'
import {fireEvent,render,screen,within} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {CollaborationComposer} from './CollaborationComposer'
import type {CollaborationPurpose} from '../api/collaboration'

it('任务建议只填写目标与类型，自写目标在类型切换及未知请求中保留',async()=>{
 const submit=vi.fn()
 function Scene({uncertain=false}:{uncertain?:boolean}){
  const [goal,setGoal]=useState(''),[purpose,setPurpose]=useState<CollaborationPurpose>('CHECK')
  return <CollaborationComposer {...{goal,setGoal,purpose,setPurpose,uncertain}} target="" setTarget={()=>{}} busy={false} error={undefined} onClose={()=>{}} onSubmit={submit}/>
 }
 const view=render(<Scene/>),suggestions=screen.getByLabelText('协作任务建议')
 fireEvent.click(within(suggestions).getByRole('button',{name:'补齐检查准备'}))
 expect((screen.getByRole('textbox',{name:'希望 Agent 完成什么'}) as HTMLTextAreaElement).value).toContain('测试账号')
 expect(screen.getByText('补齐检查准备',{selector:'.ant-select-selection-item'})).toBeVisible()
 expect(submit).not.toHaveBeenCalled()
 fireEvent.change(screen.getByRole('textbox',{name:'希望 Agent 完成什么'}),{target:{value:'只核对当前订单的备注权限'}})
 fireEvent.mouseDown(screen.getByRole('combobox',{name:'任务类型'}))
 fireEvent.click(await screen.findByRole('option',{name:'理解应用或报告'}))
 expect(screen.getByRole('textbox',{name:'希望 Agent 完成什么'})).toHaveValue('只核对当前订单的备注权限')
 view.rerender(<Scene uncertain/>)
 expect(screen.getByRole('textbox',{name:'希望 Agent 完成什么'})).toBeDisabled()
 expect(within(screen.getByLabelText('协作任务建议')).getByRole('button',{name:'整理权限要求'})).toBeDisabled()
 expect(submit).not.toHaveBeenCalled()
})
