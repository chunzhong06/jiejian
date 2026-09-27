// 业务定义先阅读后编辑；每个对象的未保存副本由父级草稿会话持有。
import { Alert, Button, Checkbox, Input, Select } from 'antd'
import { useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { BoundaryMaintenanceActorDto, BoundaryMaintenanceActionDto, BoundaryMaintenancePermissionDto, BoundaryMaintenanceDraftDto, BusinessEffectKind, ProposedEffectDto } from '../../../api/businessBoundaries'
import { effectKindLabels } from '../draft/boundaryLabels'
import { ImplementationSelector } from './ImplementationSelector'

export type DraftEffect = Omit<ProposedEffectDto,'effect_kind'> & {effect_kind?:BusinessEffectKind}
export type DraftAction = Omit<BoundaryMaintenanceActionDto,'effects'> & {effects:DraftEffect[]}
export type ObjectDrafts = Record<string, BoundaryMaintenanceActorDto | DraftAction>
const operations=[{value:'READ',label:'阅读'},{value:'CHANGE',label:'修改'},{value:'DELETE',label:'删除'},{value:'EXPORT',label:'导出'},{value:'ADMIN',label:'管理'},{value:'CUSTOM',label:'自定义'}]
const clone=<T,>(value:T):T=>JSON.parse(JSON.stringify(value)) as T
let sequence=0
const localId=(prefix:string)=>`${prefix}_${(Date.now()+ ++sequence).toString(16).padStart(16,'0').slice(-16)}`
const newEffect=():DraftEffect=>({item_id:localId('peff'),effect_id:null,business_label:'',resource_concept:'',description:'',protected_projection:[]})

export function BoundaryObjectsWorkspace({kind,actors,actions,permissions,draft,copies,setCopies,setActors,setActions,setPermissions,busy}: {
 kind:'actions'|'actors';actors:BoundaryMaintenanceActorDto[];actions:DraftAction[];permissions:BoundaryMaintenancePermissionDto[];draft:BoundaryMaintenanceDraftDto
 copies:ObjectDrafts;setCopies:Dispatch<SetStateAction<ObjectDrafts>>
 setActors:Dispatch<SetStateAction<BoundaryMaintenanceActorDto[]>>;setActions:Dispatch<SetStateAction<DraftAction[]>>
 setPermissions:Dispatch<SetStateAction<BoundaryMaintenancePermissionDto[]>>;busy:boolean
}) {
 const [selected,setSelected]=useState(actions[0]?.item_id ?? '')
 const [query,setQuery]=useState('')
 useEffect(()=>{setSelected('');setEditing(false);setQuery('');setError('')},[kind])
 const [editing,setEditing]=useState(false)
 const [error,setError]=useState('')
 const workspaceRef=useRef<HTMLElement>(null)
 const restoreEditFocus=useRef(false)
 // 保存和取消卸载表单后，键盘继续停在本对象的编辑入口。
 useEffect(()=>{if(!editing&&restoreEditFocus.current){workspaceRef.current?.querySelector<HTMLButtonElement>('.boundary-action-heading button')?.focus();restoreEditFocus.current=false}},[editing])
 const values=kind==='actions'?actions:actors
 const current=values.find(item=>item.item_id===selected)??values[0]
 const value=current && (copies[current.item_id]??current)
 const action=value && 'effects' in value?value:undefined
 const linked=current?permissions.filter(item=>kind==='actions'?item.business_action_item_id===current.item_id:item.subject_actor_item_id===current.item_id||item.resource_owner_actor_item_id===current.item_id):[]
 const update=(patch:Partial<BoundaryMaintenanceActorDto & DraftAction>)=>{if(current)setCopies(items=>({...items,[current.item_id]:{...clone(value!),...patch}}))}
 const effectUpdate=(id:string,patch:Partial<DraftEffect>)=>{if(action)update({effects:action.effects.map(item=>item.item_id===id?{...item,...patch}:item)})}
 const discard=()=>{if(current)setCopies(items=>{const next={...items};delete next[current.item_id];return next});restoreEditFocus.current=true;setEditing(false);setError('')}
 const save=()=>{
  if(!value||!current)return
  if(!value.display_name.trim()||!value.description.trim()){setError('请填写名称和业务说明。');return}
  if(action&&(!action.primary_resource_concept.trim()||!action.effects.length||action.effects.some(e=>!e.business_label.trim()||!e.resource_concept.trim()||!e.description.trim()||!e.effect_kind||(e.effect_kind==='DATA_DISCLOSURE'&&!e.protected_projection?.length)))){setError('请补齐资源概念、业务结果及其必需字段。');return}
  if(action)setActions(items=>items.map(item=>item.item_id===current.item_id?clone(action):item))
  else setActors(items=>items.map(item=>item.item_id===current.item_id?clone(value as BoundaryMaintenanceActorDto):item))
  discard()
 }
 const add=()=>{
  const item:DraftAction|BoundaryMaintenanceActorDto=kind==='actions'?{item_id:localId('pactn'),action_id:null,expected_current_revision:null,display_name:'',description:'',primary_resource_concept:'',operation_kind:'CUSTOM',state_changing:false,effects:[newEffect()],effective_state:'ACTIVE',source_candidate_ids:[]}:{item_id:localId('pactr'),actor_id:null,expected_current_revision:null,display_name:'',description:'',effective_state:'ACTIVE',source_candidate_ids:[]}
  if('effects' in item)setActions(items=>[...items,item]);else setActors(items=>[...items,item])
  setSelected(item.item_id);setCopies(items=>({...items,[item.item_id]:clone(item)}));setEditing(true)
 }
 return <><div className="boundary-collection-toolbar"><Input className="boundary-search" aria-label="搜索业务定义" placeholder={kind==='actions'?'搜索业务动作':'搜索业务角色'} allowClear value={query} onChange={e=>setQuery(e.target.value)}/><Button type="primary" disabled={busy} onClick={add}>{kind==='actions'?'新增业务动作':'新增业务角色'}</Button></div><section ref={workspaceRef} className="boundary-document definition-workspace" aria-label="业务定义">
  <aside className="action-index"><h3>{kind==='actions'?'业务动作':'业务角色'}</h3>
   <nav aria-label="业务定义索引" onKeyDown={e=>{if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;const buttons=[...e.currentTarget.querySelectorAll('button')];const at=buttons.indexOf(document.activeElement as HTMLButtonElement);if(at<0)return;e.preventDefault();buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:(at+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus()}}>{values.filter(item=>item.display_name.includes(query)).map(item=><button key={item.item_id} aria-current={current?.item_id===item.item_id?'true':undefined} onClick={()=>{setSelected(item.item_id);setEditing(false);setError('')}}>{item.display_name||'尚未命名'}<small>{copies[item.item_id]?'有未保存编辑':item.effective_state==='RETIRED'?'已停用':kind==='actions'?'业务动作':'业务角色'}</small></button>)}</nav>
   {!values.some(item=>item.display_name.includes(query))&&<p className="editorial-muted">没有匹配的定义</p>}
  </aside>
  {current&&value?<article className="boundary-action-document definition-document"><div className="boundary-action-heading"><div><p className="editorial-eyebrow">{kind==='actions'?'业务动作':'业务角色'}</p><h2>{current.display_name||'填写业务定义'}</h2></div>{!editing&&<Button disabled={busy} onClick={()=>{setCopies(items=>({...items,[current.item_id]:clone(value)}));setEditing(true)}}>{copies[current.item_id]?'继续编辑':kind==='actions'?'编辑动作':'编辑角色'}</Button>}</div>
   <span className="semantic-state">{current.effective_state==='RETIRED'?'停用草稿':'当前项目草稿'}</span>
   {editing?<div className="definition-edit-surface">
    <label>名称<Input autoFocus aria-label={kind==='actions'?'业务动作名称':'业务主体名称'} value={value.display_name} onChange={e=>update({display_name:e.target.value})}/></label>
    <label>业务说明<Input.TextArea aria-label="业务定义说明" value={value.description} autoSize={{minRows:3}} onChange={e=>update({description:e.target.value})}/></label>
    <Checkbox checked={value.effective_state==='RETIRED'} onChange={e=>update({effective_state:e.target.checked?'RETIRED':'ACTIVE'})}>停用这项定义</Checkbox>
    {action&&<><div className="definition-form-grid"><label>操作类型<Select aria-label="业务动作类型" value={action.operation_kind} options={operations} onChange={value=>update({operation_kind:value})}/></label><label>资源概念<Input aria-label="业务动作资源概念" value={action.primary_resource_concept} onChange={e=>update({primary_resource_concept:e.target.value})}/></label></div><Checkbox checked={action.state_changing} onChange={e=>update({state_changing:e.target.checked})}>会改变业务状态</Checkbox><h3>业务结果</h3>{action.effects.map(effect=><section className="boundary-effect-editor" key={effect.item_id}><label>结果名称<Input aria-label="业务结果名称" value={effect.business_label} onChange={e=>effectUpdate(effect.item_id,{business_label:e.target.value})}/></label><label>结果类型<Select aria-label="业务结果类型" value={effect.effect_kind} options={Object.entries(effectKindLabels).map(([value,label])=>({value,label}))} onChange={value=>effectUpdate(effect.item_id,{effect_kind:value})}/></label><label>资源概念<Input aria-label="业务结果资源概念" value={effect.resource_concept} onChange={e=>effectUpdate(effect.item_id,{resource_concept:e.target.value})}/></label><label>预期状态<Input aria-label="业务结果预期状态" value={effect.expected_state??''} onChange={e=>effectUpdate(effect.item_id,{expected_state:e.target.value||null})}/></label>{effect.effect_kind==='DATA_DISCLOSURE'&&<label>受保护字段<Input aria-label="业务结果有限字段" value={effect.protected_projection?.join(', ')??''} onChange={e=>effectUpdate(effect.item_id,{protected_projection:e.target.value.split(/[,，\n]/).map(v=>v.trim()).filter(Boolean)})}/></label>}<label>结果说明<Input.TextArea aria-label="业务结果说明" value={effect.description} onChange={e=>effectUpdate(effect.item_id,{description:e.target.value})}/></label><Button type="text" danger onClick={()=>update({effects:action.effects.filter(e=>e.item_id!==effect.item_id)})}>移除业务结果</Button></section>)}<Button onClick={()=>update({effects:[...action.effects,newEffect()]})}>添加业务结果</Button></>}
    <ImplementationSelector kind={kind==='actions'?'ACTION':'ROLE'} item={value} draft={draft} onChange={source_candidate_ids=>update({source_candidate_ids})}/>
    {!!linked.length&&<p className="editorial-muted">这项定义被 {linked.length} 条权限引用。停用或调整结果后，需要核对关联规则。</p>}
    {error&&<Alert className="flow-feedback" type="warning" message={error}/>}<div className="definition-edit-actions"><Button disabled={busy} onClick={discard}>取消编辑</Button>{!('effects' in value?value.action_id:value.actor_id)&&<Button type="text" danger onClick={()=>{if('effects' in value)setActions(items=>items.filter(i=>i.item_id!==current.item_id));else setActors(items=>items.filter(i=>i.item_id!==current.item_id));setPermissions(items=>items.filter(i=>i.business_action_item_id!==current.item_id&&i.subject_actor_item_id!==current.item_id&&i.resource_owner_actor_item_id!==current.item_id));discard()}}>移除未保存的新对象</Button>}<Button type="primary" disabled={busy} onClick={save}>保存到草稿</Button></div>
   </div>:<><h3 className="definition-section-label">业务含义</h3><p className="definition-description">{current.description||'尚未填写业务说明'}</p>{'effects' in current?<><dl className="definition-properties"><div><dt>操作类型</dt><dd>{operations.find(i=>i.value===current.operation_kind)?.label}</dd></div><div><dt>资源概念</dt><dd>{current.primary_resource_concept}</dd></div></dl><section className="definition-effect-summary"><h3>需要观察的业务结果</h3>{current.effects.map(effect=><div key={effect.item_id}><strong>{effect.business_label}</strong><p>{effect.description}</p></div>)}</section></>:<p className="editorial-muted">具体测试账号在准备检查时绑定。</p>}
    <section className="definition-linked"><h3>关联权限 · {linked.length}</h3>{linked.map(rule=><div className="definition-linked-rule" key={rule.item_id}><span className="permission-badge">{rule.expectation==='ALLOW'?'允许':'禁止'}</span><span>{actors.find(a=>a.item_id===rule.subject_actor_item_id)?.display_name}对{actors.find(a=>a.item_id===rule.resource_owner_actor_item_id)?.display_name}的资源，{actions.find(a=>a.item_id===rule.business_action_item_id)?.display_name}</span></div>)}</section>
   </>}
  </article>:<article className="boundary-action-document"><h2>先建立一项业务定义</h2><p>使用业务名称描述角色与动作，再编写权限要求。</p></article>}
 </section></>
}
