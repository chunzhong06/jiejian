import {useState} from 'react'
import PlusOutlined from '@ant-design/icons/PlusOutlined'
import type {ScenarioContext,ScenarioInvocation,ScenarioItem} from '../../entities/preparation/api/businessScenarios'
import {Choice} from '../../shared/ui/Choice'
import {Button} from '../../shared/ui/actions'
import {Field,SectionHeading} from '../../shared/ui/layout'

export type ScenarioOption={action:ScenarioContext['actions'][number];value:ScenarioContext['actions'][number]['cases'][number]}
export const matchesScenarioItem=(item:ScenarioItem,option:ScenarioOption)=>item.permission.intent_id===option.value.permission.intent_id&&item.permission.revision===option.value.permission.revision&&item.permission.intent_hash===option.value.permission.intent_hash&&item.subject_identity_id===option.value.subject_test_identity_id&&item.resource_id===option.value.resource_id

export function ScenarioResources({current,options,context,producers,disabled,onChange,onAdd}:{current:ScenarioInvocation;options:ScenarioOption[];context:ScenarioContext;producers:ScenarioInvocation[];disabled:boolean;onChange:(items:ScenarioItem[])=>void;onAdd:()=>void}){
  const [selected,setSelected]=useState(current.items[0].id)
  const active=current.items.find(item=>item.id===selected)??current.items[0]
  const identity=(id:string|null|undefined)=>id===null?'未登录访客':context.identities.find(item=>item.identity_id===id)?.label??'未确认'
  const optionFor=(item:ScenarioItem)=>options.find(option=>matchesScenarioItem(item,option))
  const group=optionFor(current.items[0])
  const choices=current.batch&&active.id!==current.items[0].id?options.filter(option=>option.action.action_id===group?.action.action_id&&option.value.subject_test_identity_id===group?.value.subject_test_identity_id):options
  const mismatched=Boolean(current.batch&&current.items.some(item=>{const option=optionFor(item);return !option||option.action.action_id!==group?.action.action_id||option.value.subject_test_identity_id!==group?.value.subject_test_identity_id}))
  const mixed=current.items.some(item=>optionFor(item)?.value.permission.expectation==='DENY')
  const expected=(item:ScenarioItem)=>!optionFor(item)?'准备已变化':optionFor(item)!.value.permission.expectation==='DENY'||current.batch?.strategy==='ATOMIC'&&mixed?'不应产生效果':'应产生完整效果'
  const patch=(value:Partial<ScenarioItem>)=>onChange(current.items.map(item=>item.id===active.id?{...item,...value}:item))
  return <section className="jj-scenario-resources" aria-label={current.batch?'批量资源比较':'本步操作与数据'}>
    {current.batch&&<><SectionHeading title="批量资源" level={3} meta={current.items.length+' 项'} actions={<Button kind="quiet" icon={<PlusOutlined aria-hidden="true"/>} disabled={disabled||current.items.length>=32||!options.length} onClick={onAdd}>添加资源</Button>}/>
      <div className="jj-scroll-table"><table className="jj-object-table jj-scenario-resource-table"><thead><tr><th>资源</th><th>操作账号</th><th>资源归属</th><th>本次预期</th></tr></thead><tbody>{current.items.map((item,index)=>{
        const option=optionFor(item)
        return <tr key={item.id} data-selected={active.id===item.id}><th scope="row"><button type="button" className="jj-object-select" aria-label={'编辑第 '+(index+1)+' 项资源'} aria-pressed={active.id===item.id} onClick={()=>setSelected(item.id)}>{item.resource_id}</button></th><td>{identity(item.subject_identity_id)}</td><td>{identity(option?.value.resource_owner_test_identity_id)}</td><td>{expected(item)}</td></tr>
      })}</tbody></table></div>
      <p className="jj-small jj-muted">{mismatched?'本批的动作或操作账号尚未统一。第一项确定本次请求的动作和账号，其余项须逐一选择对应资源的准确规则。':current.batch.strategy==='ATOMIC'?'整批原子：只要包含禁止项，本批每一项都不应产生效果。':'逐项处理：允许项保留正常效果，禁止项不能产生受保护效果。'}每项仍需准确的正式规则和同形正常对照。</p></>}
    <div className="jj-scenario-resource-detail"><Field label={current.batch?'调整所选资源与规则':'操作、账号与资源'}><Choice disabled={disabled} value={optionFor(active)?.value.case_id??''} placeholder="选择已准备的规则与数据" onValueChange={value=>{
      const option=options.find(entry=>entry.value.case_id===value)!
      patch({permission:{intent_id:option.value.permission.intent_id,revision:option.value.permission.revision,intent_hash:option.value.permission.intent_hash},subject_identity_id:option.value.subject_test_identity_id,resource_id:option.value.resource_id})
    }}>{choices.map(option=><option key={option.value.case_id} value={option.value.case_id}>{option.action.label} · {identity(option.value.subject_test_identity_id)} · {option.value.resource_id} · {option.value.permission.expectation==='ALLOW'?'允许':'禁止'}</option>)}</Choice></Field>
      {current.batch?current.items.length>1&&<div className="jj-scenario-local-actions"><Button kind="quiet" disabled={disabled} onClick={()=>onChange(current.items.filter(item=>item.id!==active.id))}>移除此项</Button></div>:<Field label="实际资源从哪里取得" hint="创建节点须由独立记录确认唯一新对象；模板编号仅用于准备，不会替代本轮实际编号。"><Choice disabled={disabled} value={active.resource_from??'PREPARED'} onValueChange={value=>{
        const {resource_from:omitted,...rest}=active
        void omitted
        onChange(current.items.map(item=>item.id===active.id?{...rest,...(value==='PREPARED'?{}:{resource_from:value})}:item))
      }}><option value="PREPARED">沿用已准备的资源</option>{active.resource_from&&!producers.some(node=>node.id===active.resource_from)&&<option value={active.resource_from}>原创建节点已变化，请重新选择</option>}{producers.map(node=><option key={node.id} value={node.id}>使用「{node.label}」本轮创建的对象</option>)}</Choice></Field>}
    </div>
  </section>
}
