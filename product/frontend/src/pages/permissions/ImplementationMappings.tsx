import type {BoundaryMaintenanceDraftDto} from '../../entities/permission/api/businessBoundaries'
import {Badge} from '../../shared/ui/feedback'
import {ActionLink} from '../../shared/ui/actions'
import {scopedPath} from '../../shared/lib/navigation'

export type ImplementationEdits = Record<string,string[]>

export function implementationRows(value:BoundaryMaintenanceDraftDto){
  return [
    ...value.actors.map(item=>({...item,kind:'ROLE' as const,inspection:value.implementation_inspections?.find(check=>'actor_id' in check&&check.actor_id===item.actor_id&&check.actor_revision===item.expected_current_revision)})),
    ...value.actions.map(item=>({...item,kind:'ACTION' as const,inspection:value.implementation_inspections?.find(check=>'action_id' in check&&check.action_id===item.action_id&&check.action_revision===item.expected_current_revision)})),
  ].filter(item=>item.effective_state==='ACTIVE')
}

/** 只编辑来源引用；正式角色、操作、结果和权限继续由原维护提案冻结。 */
export function ImplementationMappings({projectId,value,edits,disabled,onChange}:{projectId:string;value:BoundaryMaintenanceDraftDto;edits:ImplementationEdits;disabled:boolean;onChange:(edits:ImplementationEdits)=>void}){
  const rows=implementationRows(value),needed=rows.filter(item=>item.inspection&&item.inspection.status!=='CURRENT').length
  return <details className="jj-implementation-mappings" open={needed>0}>
    <summary>角色与操作对应{needed>0&&<Badge tone="caution">{needed} 项待核对</Badge>}</summary>
    <div className="jj-implementation-content">
      <p>把业务角色和操作对应到已确认的线索。补充或重新核对对应关系后，生成提案统一审阅。</p>
      <div className="jj-implementation-groups">{(['ROLE','ACTION'] as const).map(kind=><section key={kind}>
        <h3>{kind==='ROLE'?'业务角色':'业务操作'}</h3>
        <div className="jj-implementation-items">{rows.filter(item=>item.kind===kind).map(item=>{
          const selected=edits[item.item_id]??item.source_candidate_ids??[],options=(value.candidate_options??[]).filter(option=>option.candidate_kind===kind)
          const missing=selected.filter(id=>!options.some(option=>option.candidate_id===id))
          const replace=(ids:string[])=>onChange({...edits,[item.item_id]:ids})
          return <fieldset key={item.item_id} disabled={disabled}>
            <legend><strong>{item.display_name}</strong>{item.inspection&&<Badge tone={item.inspection.status==='CURRENT'?'neutral':'caution'}>{item.inspection.status==='CURRENT'?'已对应':item.inspection.status==='MISSING'?'尚未对应':'需要重新核对'}</Badge>}</legend>
            {options.map(option=><label className="jj-checkbox" key={option.candidate_id}><input type="checkbox" aria-label={item.display_name+'对应'+option.display_name} checked={selected.includes(option.candidate_id)} onChange={event=>replace(event.target.checked?[...selected,option.candidate_id]:selected.filter(id=>id!==option.candidate_id))}/><span>{option.display_name}</span></label>)}
            {missing.map(id=><label className="jj-checkbox" key={id}><input type="checkbox" aria-label={item.display_name+'的不可用原线索'} checked onChange={()=>replace(selected.filter(value=>value!==id))}/><span>原线索已不可用，请移除后选择当前线索。</span></label>)}
            {!options.length&&<p className="jj-small jj-muted">尚无可选择的{kind==='ROLE'?'角色':'操作'}线索。</p>}
            {item.inspection&&item.inspection.status!=='CURRENT'&&selected.length>0&&missing.length===0&&JSON.stringify([...selected].sort())===JSON.stringify([...(item.source_candidate_ids??[])].sort())&&<label className="jj-checkbox"><input type="checkbox" checked={item.item_id in edits} onChange={event=>{
              if(event.target.checked)replace(selected)
              else {const next={...edits};delete next[item.item_id];onChange(next)}
            }}/><span>已重新核对{item.display_name}的当前线索</span></label>}
          </fieldset>
        })}</div>
      </section>)}</div>
      <ActionLink kind="quiet" href={'#'+scopedPath('/application?view=business',projectId)}>补充业务角色与操作线索</ActionLink>
    </div>
  </details>
}
