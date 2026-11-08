import {useId} from 'react'

/** 即时开关只表达外部确认的状态；失败时由所属任务保留原值和恢复提示。 */
export function Switch({label,checked,onCheckedChange,disabled=false,busy=false}:{label:string;checked:boolean;onCheckedChange:(checked:boolean)=>void;disabled?:boolean;busy?:boolean}){
  const id=useId()
  return <label className="jj-switch" htmlFor={id} data-busy={busy||undefined} data-disabled={disabled||busy||undefined}>
    <input id={id} type="checkbox" role="switch" aria-label={label} aria-busy={busy||undefined} checked={checked} disabled={disabled||busy} onChange={event=>{if(!disabled&&!busy)onCheckedChange(event.target.checked)}}/>
    <span className="jj-switch-track" aria-hidden="true"><span/></span><span>{label}</span>
  </label>
}
