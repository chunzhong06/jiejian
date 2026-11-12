import {useId,useState} from 'react'
import {Button} from '../../shared/ui/actions'
import {TaskActions} from '../../shared/ui/layout'

/** 选项只修改本地决定；确认后才交给原有命令与回执流程。 */
export function RequirementDecision({label,options,confirmLabel,busy,onConfirm}:{label:string;options:ReadonlyArray<readonly [string,string]>;confirmLabel:string;busy:boolean;onConfirm:(value:string)=>void}){
  const group=useId(),[selected,setSelected]=useState('')
  return <fieldset className="jj-requirement-decision" disabled={busy}>
    <legend>{label}</legend>
    <div>{options.map(([value,text])=><label key={value}><input type="radio" name={group} value={value} checked={selected===value} onChange={()=>setSelected(value)}/><span>{text}</span></label>)}</div>
    <TaskActions><Button disabled={busy||!options.some(([value])=>value===selected)} busy={busy} onClick={()=>onConfirm(selected)}>{confirmLabel}</Button></TaskActions>
  </fieldset>
}
