import {useWorkflow} from '../../../shared/lib/workflow'
import {useId,useRef,useState} from 'react'
import type {CheckRoutine,RoutineAsset,RoutineBinding,RoutineRequirement} from '../api/routines'
import {preparationApi} from '../../preparation/api/preparation'
import {assertProject} from '../../../shared/model/page'
import {go,withReturnDestination} from '../../../shared/lib/navigation'
import {IndexSelection} from '../../../shared/ui/IndexSelection'
import {Badge,ErrorNote,Notice} from '../../../shared/ui/feedback'
import {Button} from '../../../shared/ui/actions'

type Group={kind:RoutineAsset['kind'];slot:string;label:string;minimum:number;items:RoutineAsset[];requirement?:RoutineRequirement}

export function RoutineBindingRequirements({projectId,document,assets,previous,origin,initialSlot,dirty}:{projectId:string;document:CheckRoutine;assets:RoutineAsset[];previous?:RoutineBinding;origin:string;initialSlot?:string|null;dirty:boolean}){
 const workflow=useWorkflow()
 const id=useId(),[selected,setSelected]=useState(initialSlot??''),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),lock=useRef(false)
 const declarations=document.requirements??[]
 const groups:Group[]=declarations.map(requirement=>({kind:requirement.kind,slot:requirement.slot,label:requirement.label,minimum:requirement.minimum_count,items:assets.filter(item=>item.kind===requirement.kind&&item.requirement_slot===requirement.slot),requirement}))
 groups.push(...assets.filter(item=>!declarations.some(requirement=>item.kind===requirement.kind&&item.requirement_slot===requirement.slot)).map(item=>({kind:item.kind,slot:item.slot,label:item.label,minimum:1,items:[item]})))
 const reusable=(item:Group)=>{
  const old=previous?.assets.filter(prior=>prior.kind===item.kind&&(item.requirement?prior.requirement_slot===item.slot:prior.slot===item.slot))??[]
  return item.items.length>0&&item.items.length===old.length&&item.items.every(asset=>old.some(prior=>prior.reference===asset.reference&&prior.owner_reference===asset.owner_reference&&prior.fingerprint===asset.fingerprint))
 }
 const attention=groups.filter(item=>!reusable(item)),retained=groups.filter(reusable)
 const group=groups.find(item=>item.kind+':'+item.slot===selected)??attention[0]??groups[0]
 if(!group)return <Notice>这里还没有可核对的材料。请先查看检查范围中的待准备事项，补齐后再确认用于本次检查。已有记录保留。</Notice>
 const unchanged=reusable(group)
 const prepare=async()=>{
  const requirement=group.requirement
  if(!requirement||lock.current)return;lock.current=true;setBusy(true);setError(undefined)
  try{
   const current=await preparationApi.get(projectId);assertProject(current.project_id,projectId)
   const actionRefs=declarations.filter(item=>item.kind==='FLOW').map(item=>item.action!)
   const actions=current.actions.filter(action=>actionRefs.some(ref=>ref.action_id===action.action_id&&ref.revision===action.action_revision))
   const query=new URLSearchParams()
   if(requirement.kind==='ACCOUNT'){
    const slots=actions.flatMap(action=>action.identity_requirements.slots.filter(slot=>slot.requirement.actor_id===requirement.actor?.actor_id&&slot.requirement.actor_revision===requirement.actor?.revision).map(slot=>({action,slot})))
    const target=slots.find(item=>item.slot.status!=='SATISFIED')??slots[0]
    if(!target)throw new Error('这项账号要求已变化，请核对方案所引用的业务修订。')
    query.set('action_id',target.action.action_id);query.set('identities','1');query.set('account_slot',target.slot.requirement.slot_id)
   }else{
    const action=actions.find(action=>action.action_id===requirement.action?.action_id&&action.action_revision===requirement.action?.revision)
    if(!action)throw new Error('这项操作要求已变化，请核对方案引用的修订。')
    query.set('action_id',action.action_id)
    if(requirement.kind==='RESOURCE'){
     const slots=action.identity_requirements.slots.filter(slot=>slot.requirement.actor_id===requirement.actor?.actor_id&&slot.requirement.actor_revision===requirement.actor?.revision)
     const rows=action.resources.filter(item=>slots.some(slot=>slot.requirement.slot_id===item.owner_slot_id)),target=rows.find(item=>item.status!=='SATISFIED')??rows[0]
     if(!target)throw new Error('这份测试数据还没有关联对应的所有者账号，请先核对方案要求。')
     if(target.owner_test_identity_id){query.set('material_kind','resource');query.set('member_id',target.owner_test_identity_id)}else{query.set('identities','1');query.set('account_slot',target.owner_slot_id)}
    }else{query.set('material_kind',requirement.kind==='FLOW'?'execution':'evidence');if(requirement.effect_id)query.set('member_id',requirement.effect_id)}
   }
   (workflow?.open??go)(withReturnDestination('/preparation?'+query,origin+'&binding_slot='+encodeURIComponent(group.kind+':'+group.slot)),projectId)
  }catch(error){setError(error)}finally{lock.current=false;setBusy(false)}
 }
 const title=(item:Group)=>item.kind==='ACCOUNT'?item.label+'的测试账号':item.kind==='RESOURCE'?'测试资源':item.kind==='FLOW'?'业务操作步骤':'业务结果证明'
 const explanation=group.kind==='ACCOUNT'?'本方案需要 '+group.minimum+' 个“'+group.label+'”账号。请先登录，再核对实际身份是否符合这项要求。':group.kind==='RESOURCE'?'选择这次检查要使用的测试资源，并确认它属于正确的账号。':'FLOW'===group.kind?'检查会按照已经保存的业务操作步骤进行。请核对这些步骤是否适用于这次使用的账号和资源。':'本次需要确认“'+group.label+'”是否实际发生。这里准备能够核对业务结果的记录或数据。'
 const actionLabel=group.kind==='ACCOUNT'?'去准备账号':group.kind==='RESOURCE'?'选择测试资源':group.kind==='FLOW'?'核对操作步骤':'配置结果证明'
 return <div className="jj-routine-binding-layout" data-single={groups.length===1||undefined}>{groups.length>1&&<nav aria-label="本次检查需要的材料"><IndexSelection identity={group.kind+':'+group.slot}>{attention.map(item=><button key={item.kind+':'+item.slot} className="jj-index-item" aria-current={group===item?'true':undefined} onClick={()=>{setSelected(item.kind+':'+item.slot);setError(undefined)}}><strong>{title(item)}</strong><small>{item.items.length?'已有材料，等待确认':'需要准备'}</small></button>)}</IndexSelection>{retained.length>0&&<details className="jj-routine-retained"><summary>可沿用的已确认材料 · {retained.length}</summary><IndexSelection identity={group.kind+':'+group.slot}>{retained.map(item=><button className="jj-index-item" key={item.kind+':'+item.slot} aria-current={group===item?'true':undefined} onClick={()=>setSelected(item.kind+':'+item.slot)}><strong>{title(item)}</strong><small>与上次确认一致</small></button>)}</IndexSelection></details>}</nav>}
  <section className="jj-routine-binding-reading" aria-labelledby={id}>
   <header className="jj-routine-binding-heading"><p className="jj-eyebrow">本次检查准备</p><div className="jj-object-line"><h3 id={id}>{title(group)}</h3><Badge tone={unchanged?'positive':'neutral'}>{unchanged?'沿用上次确认的材料':group.items.length?'已有材料，等待确认':'需要准备'}</Badge></div></header>
   <div className="jj-routine-binding-body">
    <section aria-label="使用要求"><h4 className="jj-title-caption">使用要求</h4><p className="jj-routine-explanation">{explanation}</p>
     {group.requirement?.normal_control_required&&<p className="jj-small jj-muted">同时保留正常访问的对照，确认业务仍可正常使用。</p>}
     {group.requirement?.recovery_required&&<p className="jj-small jj-muted">这项操作会改变业务状态，还需准备恢复测试数据的方式。</p>}
    </section>
    <section aria-label="当前材料"><h4 className="jj-title-caption">{group.kind==='ACCOUNT'?'当前账号':group.kind==='RESOURCE'?'当前测试资源':group.kind==='FLOW'?'当前操作步骤':'当前结果证明'}</h4>
     {group.items.length?<div className="jj-routine-bound-items">{group.items.map(item=><div key={item.kind+':'+item.slot}><strong>{item.label}</strong><details><summary>核对材料记录</summary><code>{item.reference}</code></details></div>)}</div>:<p className="jj-muted">{group.kind==='ACCOUNT'?'尚未准备可用于本次检查的账号。':group.kind==='RESOURCE'?'尚未选择本次检查使用的测试资源。':group.kind==='FLOW'?'尚未确认本次检查使用的操作步骤。':'尚未配置能够核对这项业务结果的证明。'}</p>}
    </section>
   </div>
   {Boolean(error)&&<ErrorNote error={error}/>}
   {group.requirement&&!dirty&&<footer className="jj-routine-binding-footer"><Button kind="default" busy={busy} onClick={()=>void prepare()}>{actionLabel}</Button></footer>}
  </section></div>
}
