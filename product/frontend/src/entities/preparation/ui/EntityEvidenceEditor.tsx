import {useEffect,useRef,useState,type ComponentProps} from 'react'
import type {EntityEvidence} from '../api/operationFlows'
import {Field} from '../../../shared/ui/layout'

export type EvidenceEffect={effect_id:string;label:string;kind:string;protected_projection:string[]}
export function EntityEvidenceEditor({effects,value,onChange}:{effects:EvidenceEffect[];value:EntityEvidence[];onChange:(items:EntityEvidence[])=>void}) {
  const available=effects.filter(item=>item.kind==='DATA_DISCLOSURE')
  if(!available.length)return null
  const update=(effect:string,query:EntityEvidence['query'])=>onChange(value.map(item=>item.effect_id===effect?{...item,query}:item))
  return <section className="jj-flow-evidence"><header><h3>独立查询（可选）</h3><p className="jj-small jj-muted">勾选业务结果后配置查询，以资源所有者的响应作为对照。也可以在检查准备中使用其他结果证明。</p></header>{available.map(effect=>{const selected=value.find(item=>item.effect_id===effect.effect_id);return <section key={effect.effect_id}><label className="jj-checkbox"><input type="checkbox" checked={Boolean(selected)} onChange={event=>onChange(event.target.checked?[...value,{effect_id:effect.effect_id,query:{request:{method:'GET',path:'/resources/{case_resource_id}',input_slots:[{slot_id:'case_resource_id',source:'CASE_RESOURCE_ID',consumer:'PATH',consumer_step_id:'entity_query'}]},resource_path:'$.id',owner_path:'$.owner_id',data_path:'$'}}]:value.filter(item=>item.effect_id!==effect.effect_id))}/>{effect.label}</label><p className="jj-small jj-muted">受保护字段：{effect.protected_projection.join('、')}</p>{selected&&<div className="jj-form-grid"><Field measure="standard" label="所有者查询路径" hint="包含完整资源参数 {case_resource_id}。"><input value={selected.query.request.path as string} onChange={event=>update(effect.effect_id,{...selected.query,request:{...selected.query.request,path:event.target.value}})}/></Field>{(['resource_path','owner_path','data_path'] as const).map(key=><Field measure="standard" key={key} label={{resource_path:'资源编号字段',owner_path:'所有者编号字段',data_path:'业务数据所在位置'}[key]}><input value={selected.query[key]} onChange={event=>update(effect.effect_id,{...selected.query,[key]:event.target.value})}/></Field>)}<Field measure="standard" label="资源状态字段（可选）" hint="仅在要求包含资源状态时配置，状态取自本次独立查询。"><input value={selected.query.condition_state_path??''} placeholder="$.status" onChange={event=>update(effect.effect_id,{...selected.query,condition_state_path:event.target.value||null,...(!event.target.value?{condition_state_values:[]}:{})})}/></Field>{selected.query.condition_state_path&&<Field measure="standard" label="允许采集的公开状态" hint="用逗号分隔，例如 DRAFT, APPROVED；未列出的实际值不会写入结果。"><PublicStates value={selected.query.condition_state_values??[]} onChange={values=>update(effect.effect_id,{...selected.query,condition_state_values:values})}/></Field>}</div>}</section>})}<p className="jj-flow-evidence-scope jj-small jj-muted">比较上述 JSON 字段；资源状态仅使用已确认的有限公开值。查询失败、账号或资源不对应、响应不完整时，会提示证据缺口。保存并确认使用场景时，一并确认这里的查询与字段范围。</p></section>
}

/** 保留输入中的尾随分隔符；规范化数组不应打断连续输入第二个状态。 */
function PublicStates({value,onChange,...labels}:Omit<ComponentProps<'input'>,'value'|'onChange'>&{value:string[];onChange:(value:string[])=>void}){
  const serialized=JSON.stringify(value)
  const published=useRef(serialized)
  const [text,setText]=useState(value.join(', '))
  useEffect(()=>{if(serialized!==published.current){published.current=serialized;setText(value.join(', '))}},[serialized])
  return <input {...labels} value={text} onChange={event=>{const next=event.target.value;setText(next);const values=next.split(/[,，]/).map(value=>value.trim()).filter(Boolean);published.current=JSON.stringify(values);onChange(values)}}/>
}
