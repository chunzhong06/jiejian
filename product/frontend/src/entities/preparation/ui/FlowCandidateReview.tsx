import type {FlowEditorDraft} from './flowDraft'
import {useState} from 'react'
import type {OperationFlow} from '../api/operationFlows'
import type {EditableStep} from './flowInputs'
import {decodeSteps} from './flowInputs'
import {Dialog} from '../../../shared/ui/Dialog'
import {Button} from '../../../shared/ui/actions'

export const flowDraftKey=(project:string,action:string)=>'flow:'+project+':'+action

export function FlowCandidateReview({candidate,previous,accounts,onApply,onKeep}:{candidate:OperationFlow;previous?:FlowEditorDraft;accounts:{identity_id:string;label:string}[];onApply:(preserveValues:boolean)=>void;onKeep:()=>void}){
  const [preserve,setPreserve]=useState(true)
  const accountLabel=(id:string|undefined)=>accounts.find(item=>item.identity_id===id)?.label??'尚未选择或账号已不可用'
  const inputs=(steps:EditableStep[])=>steps.flatMap(step=>{
    const parameters:Pick<EditableStep['parameters'][number],'name'|'location'|'source'>[]=[...step.parameters]
    if(step.path.includes('{case_resource_id}')&&!parameters.some(item=>item.name==='case_resource_id'&&item.location==='PATH'))parameters.push({name:'case_resource_id',location:'PATH',source:'CASE_RESOURCE_ID'})
    return parameters.map(item=>({PATH:'路径',QUERY:'查询',HEADER:'请求头',JSON_BODY:'正文'}[item.location])+' · '+item.name+' ← '+(item.source==='CASE_RESOURCE_ID'?'测试数据编号':item.source==='CASE_SUBJECT_ID'?'操作账号':item.source==='LITERAL'?'固定值':'前序请求取值'))
  }).join('\n')||'没有额外参数'
  const rows=[
    ['执行请求',previous?.steps.map(step=>step.method+' '+step.path).join('\n')??'尚无草稿',candidate.workflow.steps.map(step=>step.request_template.method+' '+step.request_template.path).join('\n')],
    ['受检步骤',previous?String(previous.steps.findIndex(step=>step.id===previous.target)+1):'未选择',String(candidate.workflow.steps.findIndex(step=>step.id===candidate.workflow.target_step_id)+1)],
    ['操作账号',accountLabel(previous?.subject||accounts[0]?.identity_id),accountLabel(candidate.subject_test_identity_id)],
    ['资源所有者',accountLabel(previous?.owner||accounts[0]?.identity_id),accountLabel(candidate.resource_owner_test_identity_id)],
    ['测试数据',previous?.resource||'未填写',candidate.actual_resource_id],
    ['结果查询',previous?.entityEvidence.map(item=>String(item.query.request.path)+' · '+item.query.data_path).join('\n')||'未设置',candidate.entity_evidence?.map(item=>String(item.query.request.path)+' · '+item.query.data_path).join('\n')||'未设置'],
    ['参数与取值来源',inputs(previous?.steps??[]),inputs(decodeSteps(candidate.workflow.steps))],
    ['恢复请求',previous?.recovery?previous.restoreMethod+' '+previous.recovery:'未设置',candidate.recovery?candidate.recovery.method+' '+candidate.recovery.relative_path:'无需恢复'],
  ]
  return <Dialog title={'审阅流程候选 · 第 '+candidate.revision+' 修订'} onClose={onKeep} actions={<><Button onClick={onKeep}>保留当前草稿</Button><Button kind="primary" onClick={()=>onApply(preserve)}>带入候选继续核对</Button></>}>
    <p>比较 Agent 保存的准确修订。带入后可以继续编辑，尚未用于正式检查。</p>
    <div className="jj-flow-candidate-diff"><table><thead><tr><th>内容</th><th>当前草稿</th><th>Agent 候选</th></tr></thead><tbody>{rows.map(([label,before,after])=><tr key={label} data-changed={before!==after}><th scope="row">{label}</th><td>{before}</td><td>{after}</td></tr>)}</tbody></table></div>
    {previous&&<label className="jj-checkbox"><input type="checkbox" checked={preserve} onChange={event=>setPreserve(event.target.checked)}/><span>沿用同一步骤中同名参数的已填写值<small>这些值没有交接给 Agent。参数位置和来源一致时保留；结构变化请在编辑器中核对。</small></span></label>}
  </Dialog>
}
