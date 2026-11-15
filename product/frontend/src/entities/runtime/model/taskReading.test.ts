import {expect,it} from 'vitest'
import {collaborationOutputs,collaborationTitle} from './taskReading'
import type {CollaborationTask} from '../api/collaboration'

it('任务名称使用明确说明，旧长目标不截句，短目标保持原文',()=>{
 expect(collaborationTitle({goal:'发布资料',purpose:'SETUP'})).toBe('发布资料')
 expect(collaborationTitle({goal:'内部指令'.repeat(50),purpose:'SETUP'})).toBe('补齐检查准备')
 expect(collaborationTitle({goal:'内部指令'.repeat(50),purpose:'SETUP',brief:{title:'准备发布检查',objective:'',outputs:[]}})).toBe('准备发布检查')
})

it('交付进展只统计当前目标之后成功保存的独立对象，不以修订数量或待审请求充当完成',()=>{
 const task={brief:{outputs:[{kind:'FLOW',label:'发布与恢复步骤'},{kind:'PROOF',label:'发布结果依据'}]},goal_operation_baseline:1,operations:[{state:'SUCCEEDED',capability:'proofs.save',result:{source_id:'old',revision:1}},{state:'SUCCEEDED',capability:'flows.save',result:{id:'flow',revision:2}},{state:'SUCCEEDED',capability:'flows.save',result:{id:'flow',revision:3}},{state:'WAITING_USER',capability:'proofs.save',result:{source_id:'unaccepted',revision:1}}]} as CollaborationTask
 expect(collaborationOutputs(task)).toEqual([{kind:'FLOW',label:'发布与恢复步骤',saved:1},{kind:'PROOF',label:'发布结果依据',saved:0}])
})
